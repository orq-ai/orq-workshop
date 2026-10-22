"""make chat: talk to the refund agent in a browser, one link to the trace per answer.

What: four routes. `GET /` serves `web/index.html`; `GET /api/models` lists the models the
picker offers; `GET /api/backend` is the read-only orders and policies for the sidebar;
`POST /api/chat` runs one turn and returns the answer, the tools called, the trace id and a
Studio link to that trace. A plain model id runs the same local `chat()` every module
uses (our loop, our tools); `agent/<prefix>-refund-agent` is one call to the agent that
`make seed` provisions in orq, where orq runs the loop and the tools as code tools.
Why: a transcript in a browser is easier to read than a terminal, and the trace link closes the
loop from "what did the agent say" to "what did it do".
How: `make chat` (or `uv run python -m app.web`), then open http://127.0.0.1:8002. Stateless like
the rest of the repo (Factor 12): the browser sends back the full `history` it got last time. The
one thing kept server-side is an `OrderStore` per `conversation_id`, so a refund issued in turn 1
is still refunded in turn 2; it lives in memory and resets when the server restarts.

Request:  {"message": str, "history": [...], "conversation_id": str, "model": str}  (all but message optional)
Response: {"answer", "tool_calls", "trace_id", "trace_url", "history", "model", "seconds"}
"""

from __future__ import annotations

import contextlib
import copy
import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx
import uvicorn
from openai import APIStatusError, OpenAIError
from starlette.applications import Starlette
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from app import insurance
from app.refund_agent import tools
from app.refund_agent.agent import (
    HANDOFF_TEXT,
    IDENTITY_HEADER,
    MAX_TOOL_ROUNDS,
    TRACE_HEADER,
    _propagation_headers,
    chat,
    system_message,
)
from app.refund_agent.client import make_openai_client, make_orq
from app.refund_agent.config import ROOT, settings
from app.refund_agent.entities import CHAT_CHANNELS
from app.refund_agent.tools import OrderStore

INDEX_HTML = ROOT / "web" / "index.html"
PORT = 8002
FONTS = ROOT / "docs" / "stylesheets" / "fonts"  # the page uses the docs site's typeface
ORDER_FIELDS = ("id", "item", "amount", "delivered_days_ago", "refunded")  # never owner_id or notes
_busy: set[str] = set()  # conversations with a turn in flight: a second one would race on the same orders
_stores: dict[str, OrderStore] = {}  # conversation_id -> its orders; in memory, per process
# Shown when the key cannot list models (the workshop key gets 403 "Missing permission:
# model.view"). Each answered through the gateway on 14 Oct 2026.
FALLBACK_MODELS = [
    "openai/gpt-6-luna",
    "openai/gpt-6-astra",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.4-nano",
    "anthropic/claude-haiku-4-5-20251001",
]


def trace_url(trace_id: str | None) -> str | None:
    """Studio deep link to one trace; the Traces page when ORQ_WORKSPACE is not set."""
    if not trace_id:
        return None
    workspace = settings.studio_workspace()
    if not workspace:
        return f"{settings.base_url}/traces"
    # Studio route: /traces/(trace:<id>), optionally //span:<id>; we only have the trace id
    return f"{settings.base_url}/{quote(workspace, safe='')}/traces/(trace:{quote(trace_id, safe='')})"


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def index(request: Request) -> FileResponse:
    return FileResponse(INDEX_HTML)


def _workspace_models() -> list[str]:
    """The workspace's enabled chat models that can call tools, from `GET /v2/models`.

    FALLBACK_MODELS when the key may not list models (403) or the call fails. The agent calls
    tools every turn, so classifiers, embedders and chat models without function calling are out.
    """
    try:
        response = httpx.get(
            f"{settings.base_url}/v2/models",
            headers={"Authorization": f"Bearer {settings.bearer()}"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError, SystemExit):
        return FALLBACK_MODELS
    ids = [
        f"{m['provider']}/{m['model_id']}"
        for m in rows
        if m.get("enabled") and m.get("model_type") == "chat" and m.get("has_functions")
    ]
    return ids or FALLBACK_MODELS


def hosted_agent() -> str:
    """The model id of the agent whose tools run in orq (`entities.ensure_agent`, code tools)."""
    return f"agent/{settings.key('refund-agent')}"


def _hosted_agent_exists() -> bool:
    try:
        make_orq().agents.retrieve(agent_key=hosted_agent().removeprefix("agent/"))
        return True
    except (Exception, SystemExit):  # noqa: BLE001  not seeded, not readable or no credentials: leave it out
        return False


def _workspace_agents() -> list[str]:
    """`agent/<key>` for every live agent in the workspace, the seeded refund agent first.

    Versioned copies (`<key>_<ULID>`) are left out. Empty when the key cannot list agents: the
    caller then falls back to checking only the seeded one.
    """
    try:
        response = httpx.get(
            f"{settings.base_url}/v2/agents",
            headers={"Authorization": f"Bearer {settings.bearer()}"},
            params={"limit": 200},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json().get("data") or []
    except (httpx.HTTPError, ValueError, SystemExit):
        return []
    keys = [r["key"] for r in rows if r.get("key") and r.get("status", "live") == "live"
            and not re.search(r"_[0-9A-Za-z]{26}$", r["key"])]
    first = hosted_agent().removeprefix("agent/")
    return [f"agent/{k}" for k in sorted(keys, key=lambda k: (k != first, k.lower()))]


def backend_view() -> dict[str, Any]:
    """The sidebar's read-only projection: the session user's orders without owner ids or notes
    (which hold another customer's contact details), and the policy files `get_policy` serves."""
    owned = [o for o in tools._FIXTURE["orders"] if o["owner_id"] == tools._FIXTURE["session_user_id"]]
    return {
        "orders": [{field: order[field] for field in ORDER_FIELDS} for order in owned],
        "policies": [
            {"topic": topic, "text": (tools.KB_DIR / f"{topic}.md").read_text()} for topic in tools.POLICY_TOPICS
        ],
    }


def insurance_view() -> dict[str, Any]:
    """The Insurance demo's sidebar and prompts: test cases, rules, example messages, guardrail choices."""
    return {
        "cases": insurance.test_cases(),
        "rules": insurance.rules(),
        "prompts": insurance.prompts(),
        "guardrails": [
            ["", "Off"],
            ["input", "IBAN/BSN, injection · input"],
            ["output", "IBAN/BSN, cents · output"],
            ["legal", "No legal advice · output"],
            ["payout", "Payout limit · output"],
            ["all", "All four"],
        ],
    }


def _insurance_default(agents: list[str]) -> str | None:
    """The claims agent the Insurance demo starts on: ours (`<prefix>-claims-assessor`), else the cookbook's."""
    for key in (*insurance.agent_keys()[:1], "claims-assessor"):
        if f"agent/{key}" in agents:
            return f"agent/{key}"
    return None


async def get_backend(request: Request) -> JSONResponse:
    if request.query_params.get("demo") == "insurance":
        return JSONResponse(insurance_view())
    return JSONResponse(backend_view())


async def get_models(request: Request) -> JSONResponse:
    """The picker's options: the configured MODEL first and selected, then every live agent of the workspace."""
    models = await run_in_threadpool(_workspace_models)
    agents = await run_in_threadpool(_workspace_agents)
    if not agents and await run_in_threadpool(_hosted_agent_exists):
        agents = [hosted_agent()]
    return JSONResponse(
        {
            "default": settings.model,
            "models": [settings.model, *(m for m in models if m != settings.model)],
            "agents": agents,
            "insurance_default": _insurance_default(agents),  # None until the claims agents exist
        }
    )


def _tool_outcomes(messages: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    """The tools this turn called, each with what it returned: `ok` and the short `error`.

    Pairs `function_call` items with their `function_call_output` by call_id. The last
    `len(names)` calls are this turn's; earlier ones belong to the history.
    """
    calls = [m for m in messages if m.get("type") == "function_call"][len(names) * -1 :] if names else []
    wanted = {c["call_id"] for c in calls}
    results = {}
    for m in messages:  # the history comes from the browser: ignore outputs that are not JSON objects
        if m.get("type") == "function_call_output" and m.get("call_id") in wanted:
            try:
                parsed = json.loads(m["output"])
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                results[m["call_id"]] = parsed
    return [
        {"name": c["name"], "ok": r.get("ok"), "error": r.get("error")}
        for c in calls
        for r in [results.get(c["call_id"], {})]
    ]


def _blocked(exc: APIStatusError) -> dict[str, Any] | None:
    """What the gateway's guardrail said, or None when this error is not a guardrail block."""
    body = exc.body if isinstance(exc.body, dict) else {}
    if body.get("code") != "guardrail_error":
        return None
    return {
        "failures": [
            {"id": f.get("id"), "stage": f.get("stage"), "reason": f.get("reason")}
            for f in body.get("failures") or []
        ],
        "trace_id": exc.response.headers.get(TRACE_HEADER),
    }


def _transcript(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The user and assistant text of the conversation: an orq agent has its own instructions and tools."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]


def _sub_agent(arguments: Any) -> str | None:
    """The agent key in the arguments of an orchestrator's `call_sub_agent` call."""
    try:
        key = json.loads(arguments).get("agent_key")
    except (TypeError, ValueError, AttributeError):
        return None
    return key if isinstance(key, str) else None


def _clip(text: Any, limit: int = 600) -> str | None:
    """A string cut to `limit` characters, for the sidebar; None when there is nothing to show."""
    if not isinstance(text, str) or not text:
        return None
    return text if len(text) <= limit else text[:limit] + "…"


def _call(name: str, arguments: Any, result: Any = None) -> dict[str, Any]:
    """One tool call of an orq agent for the UI. A sub-agent call shows its `input` text and the agent's `result`."""
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        parsed = None
    parsed = parsed if isinstance(parsed, dict) else {}
    sub = name == "call_sub_agent"
    return {
        "name": name, "ok": None, "error": None, "agent": _sub_agent(arguments) if sub else None,
        "input": _clip(parsed.get("input") if sub else arguments), "result": _clip(result),
    }


def _hosted_turn(
    model: str, message: str, history: list[dict[str, Any]], extra_body: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], str | None, list[dict[str, Any]], list[str]]:
    """One turn on an agent that lives in orq: one Responses call, orq runs the loop and the tools.

    The agent has its own instructions and tools, so it gets only the text of the conversation
    (user and assistant messages), not our system prompt or our tool items. The history we return
    is the browser's plus this exchange, so the conversation can switch back to a plain model.
    The last item is the sub-agents the agent called, in order, for the minimap to replay.
    """
    raw = make_openai_client().responses.with_raw_response.create(
        model=model,
        input=[*_transcript(history), {"role": "user", "content": message}],
        extra_body=extra_body,
        extra_headers={IDENTITY_HEADER: settings.identity_id},
    )
    response = raw.parse()
    answer = response.output_text
    results = {  # orq runs a sub-agent in an `orq:call_sub_agent` item next to the call: its text is the result
        item.call_id: (item.model_extra or {}).get("result")
        for item in response.output if item.type == "orq:call_sub_agent"
    }
    tool_calls = [_call(item.name, item.arguments, results.get(item.call_id)) for item in response.output if item.type == "function_call"]
    steps = [
        key for item in response.output
        if item.type == "function_call" and item.name == "call_sub_agent" and (key := _sub_agent(item.arguments))
    ]
    turn = [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    return answer, tool_calls, raw.headers.get(TRACE_HEADER), [*history, *turn], steps


def _step(call_id: str, call: dict[str, Any], state: str) -> dict[str, Any]:
    """A `step` event: one tool call of the agent (a sub-agent call has `agent`), `running` or `done`."""
    return {
        "type": "step", "id": call_id, "tool": call["name"], "agent": call["agent"], "state": state,
        "input": call["input"], "result": call["result"], "ok": call.get("ok"), "error": call.get("error"),
    }


def _stream_turn(model: str, message: str, history: list[dict[str, Any]], extra_body: dict[str, Any]):
    """The same turn as `_hosted_turn`, as UI events while orq generates it (a sync generator).

    `node`: an agent starts or finishes (`working` / `done`; the agent itself is `root`).
    `step`: a tool call starts or finishes, keyed by its call id (the run sidebar's chain).
    `delta`: a piece of the answer. `done`: the finished turn, shaped like the /api/chat reply.
    Raises APIStatusError before the first event when the gateway rejects the request.
    """
    raw = make_openai_client().responses.with_raw_response.create(
        model=model,
        input=[*_transcript(history), {"role": "user", "content": message}],
        extra_body=extra_body,
        extra_headers={IDENTITY_HEADER: settings.identity_id},
        stream=True,
    )
    trace_id = raw.headers.get(TRACE_HEADER)
    agent_of_call: dict[str, str] = {}  # call_id -> the sub-agent the orchestrator asked for
    answer, calls, steps = "", {}, []
    yield {"type": "start", "trace_id": trace_id}
    for event in raw.parse():
        kind, item = event.type, getattr(event, "item", None)
        if kind == "response.created":
            yield {"type": "node", "agent": "root", "state": "working"}
        elif kind == "response.output_item.added" and item.type == "function_call":
            yield _step(item.call_id, _call(item.name, None), "running")
        elif kind == "response.output_item.done" and item.type == "function_call":
            call = calls[item.call_id] = _call(item.name, item.arguments)
            if key := call["agent"]:
                agent_of_call[item.call_id] = key
                steps.append(key)
            yield _step(item.call_id, call, "running" if key else "done")  # a sub-agent runs on until its orq item is done
        elif kind == "response.output_item.added" and item.type == "orq:call_sub_agent":
            key = agent_of_call.get(item.call_id) or _sub_agent(item.arguments)
            if key:
                yield {"type": "node", "agent": key, "state": "working"}
        elif kind == "response.output_item.done" and item.type == "orq:call_sub_agent":
            if key := agent_of_call.get(item.call_id):
                yield {"type": "node", "agent": key, "state": "done"}
                call = calls[item.call_id]
                call["result"] = _clip((item.model_extra or {}).get("result"))
                yield _step(item.call_id, call, "done")
        elif kind == "response.output_text.delta":
            answer += event.delta
            yield {"type": "delta", "text": event.delta}
        elif kind == "response.completed":
            answer = event.response.output_text or answer
    yield {"type": "node", "agent": "root", "state": "done"}
    turn = [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    yield {
        "type": "done", "answer": answer, "tool_calls": list(calls.values()),
        "trace_id": trace_id, "trace_url": trace_url(trace_id), "history": [*history, *turn], "steps": steps,
    }


def _stream_local_turn(model: str, message: str, history: list[dict[str, Any]], store: OrderStore, extra_body: dict[str, Any]):
    """`agent.run_turn` with each model round streamed: the same loop and tools, as UI events (a sync generator).

    Same events as `_stream_turn`; the tools run here, so a `step` ends with the tool's `ok` and
    `error`. Raises APIStatusError before the first event when the gateway rejects the request.
    """
    client = make_openai_client()
    messages = list(history)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_message())
    messages.append({"role": "user", "content": message})
    instructions = messages.pop(0)["content"]  # the Responses API takes the system prompt as `instructions`
    headers = {**_propagation_headers(), IDENTITY_HEADER: settings.identity_id}
    outcomes: list[dict[str, Any]] = []
    trace_id = None
    for round_ in range(MAX_TOOL_ROUNDS + 1):
        raw = client.responses.with_raw_response.create(
            model=model, instructions=instructions, input=messages, tools=tools.RESPONSES_TOOLS, store=False,
            extra_body=extra_body or {}, extra_headers=headers, stream=True,
        )
        trace_id = raw.headers.get(TRACE_HEADER) or trace_id
        if round_ == 0:
            yield {"type": "start", "trace_id": trace_id}
            yield {"type": "node", "agent": "root", "state": "working"}
        text, calls = "", []
        for event in raw.parse():
            item = getattr(event, "item", None)
            if event.type == "response.output_text.delta":
                text += event.delta
                yield {"type": "delta", "text": event.delta}
            elif event.type == "response.output_item.added" and item.type == "function_call":
                yield _step(item.call_id, _call(item.name, None), "running")
            elif event.type == "response.output_item.done" and item.type == "function_call":
                calls.append(item)
        if text:
            messages.append({"role": "assistant", "content": text})
        for item in calls:
            messages.append({"type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments})
        if not calls:
            break
        for item in calls:
            result = tools.dispatch(store, item.name, json.loads(item.arguments or "{}"))
            messages.append({"type": "function_call_output", "call_id": item.call_id, "output": json.dumps(result)})
            call = _call(item.name, item.arguments, json.dumps(result))
            call["ok"], call["error"] = result.get("ok"), result.get("error")
            outcomes.append(call)
            yield _step(item.call_id, call, "done")
    else:  # out of rounds: hand off to a human, as run_turn does
        messages.append({"role": "assistant", "content": HANDOFF_TEXT})
        yield {"type": "delta", "text": HANDOFF_TEXT}
    answer = next((m["content"] for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")), "")
    yield {"type": "node", "agent": "root", "state": "done"}
    yield {
        "type": "done", "answer": answer, "tool_calls": outcomes, "trace_id": trace_id, "trace_url": trace_url(trace_id),
        "history": [system_message(instructions), *messages], "steps": [],
    }


_graphs: dict[str, dict[str, Any]] = {}  # agent key -> its sub-agent graph; agents rarely change while the chat runs
_eval_names: dict[str, str] = {}  # evaluator id -> key without the workshop prefix


def _evaluator_names(orq) -> dict[str, str]:
    """Evaluator id -> readable key, read once: an agent lists its evaluators and guardrails by id only."""
    if not _eval_names:
        with contextlib.suppress(Exception):  # names are a nicety: the sidebar falls back to the id
            for ev in orq.evals.all(limit=50).data or []:
                if getattr(ev, "id", None) and getattr(ev, "key", None):
                    _eval_names[ev.id] = ev.key.removeprefix(f"{settings.prefix}-")
    return _eval_names


def _agent_parts(settings_: dict[str, Any], names: dict[str, str]) -> tuple[list[str], list[dict[str, Any]]]:
    """(tool names, checks) of an agent's settings. A check is an evaluator (scores) or a guardrail (blocks)."""
    tools = [t.get("display_name") or t.get("action_type") or t.get("key") or "tool" for t in settings_.get("tools") or []]
    checks = [
        {"name": names.get(c.get("id"), str(c.get("id"))[-6:]), "kind": kind, "stage": c.get("execute_on"), "rate": c.get("sample_rate")}
        for kind in ("guardrail", "evaluator")
        for c in settings_.get(kind + "s") or []
    ]
    return tools, checks


def _agent_graph(key: str) -> dict[str, Any]:
    """Nodes and edges of an agent and the sub-agents it can call, three levels deep.

    {"root": key, "nodes": [{"id", "label", "tools", "checks"}], "edges": [[parent, child]]}. A
    single agent has one node and no edges: the minimap stays hidden for it, the sidebar still lists
    its tools and checks.
    """
    if key in _graphs:
        return _graphs[key]
    orq, seen, edges, queue = make_orq(), {key: None}, [], [(key, 0)]  # seen: insertion-ordered
    parts: dict[str, tuple[list[str], list[dict[str, Any]]]] = {}
    while queue:
        current, depth = queue.pop(0)
        if depth >= 3:
            continue
        try:
            agent = orq.agents.retrieve(agent_key=current).model_dump()
            team = agent.get("team_of_agents") or []
            parts[current] = _agent_parts(agent.get("settings") or {}, _evaluator_names(orq))
        except Exception:  # noqa: BLE001  a member that cannot be read is a leaf in the map
            team = []
        for member in team:
            child = member.get("key")
            if not child:
                continue
            edges.append([current, child])
            if child not in seen:
                seen[child] = None
                queue.append((child, depth + 1))
    prefix = f"{settings.prefix}-"
    graph = {
        "root": key,
        "nodes": [
            {"id": k, "label": k.removeprefix(prefix), "tools": parts.get(k, ([], []))[0], "checks": parts.get(k, ([], []))[1]}
            for k in sorted(seen, key=lambda k: k != key)
        ],
        "edges": edges,
    }
    if key in parts:  # a lookup that failed must not stick
        _graphs[key] = graph
    return graph


async def get_agent_graph(request: Request) -> JSONResponse:
    model = request.query_params.get("model", "")
    if not model.startswith("agent/"):
        return JSONResponse({"root": None, "nodes": [], "edges": []})
    try:
        return JSONResponse(await run_in_threadpool(_agent_graph, model.removeprefix("agent/")))
    except (OpenAIError, SystemExit) as exc:
        return _error(502, f"could not read the agent: {exc}")


async def _chat_context(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Validate a chat request and reserve its conversation: (context, None) or (None, error reply).

    The caller must `_release` the context when the turn ends, however it ends.
    """
    try:
        await run_in_threadpool(settings.bearer)  # API key, else the `orq auth login` session
    except SystemExit as exc:
        return None, _error(500, str(exc))
    try:
        body = await request.json()
    except ValueError:
        return None, _error(400, "body must be JSON")
    if not isinstance(body, dict):
        body = {}
    message = body.get("message")
    history = body.get("history") or []
    conversation_id = str(body.get("conversation_id") or "")
    model = body.get("model") or settings.model
    if (
        not isinstance(message, str)
        or not message.strip()
        or not isinstance(history, list)
        or not isinstance(model, str)
    ):
        return None, _error(422, "expected {message: non-empty string, history: list, model: string}")

    store = OrderStore()
    extra_body: dict[str, Any] = {"name": "refund-chat"}
    demo = body.get("demo") or "refund"
    if demo not in ("refund", "insurance"):
        return None, _error(422, "demo must be refund or insurance")
    if demo == "insurance" and not model.startswith("agent/"):
        return None, _error(422, "the insurance demo chats with orq agents: pick an agent")
    if demo == "insurance":
        extra_body["name"] = "insurance-chat"
    channels = insurance.CHANNELS if demo == "insurance" else CHAT_CHANNELS
    choice = {True: "both", None: "", False: ""}.get(body.get("guardrails"), body.get("guardrails"))
    if choice and choice not in channels:
        return None, _error(422, f"guardrails must be one of {sorted(channels)} or empty")
    if choice:
        # Responses ignores request-level `guardrails`; a rule matching this tag guards the call.
        # `make seed` / `make seed-insurance` create the rules; they are admin-only, so a workshop
        # key cannot read them back.
        extra_body["metadata"] = {"channel": channels[choice]}
    snapshot = None
    if conversation_id:
        if conversation_id in _busy:
            return None, _error(409, "this conversation is still answering the previous message")
        _busy.add(conversation_id)
        store = _stores.setdefault(conversation_id, store)
        snapshot = copy.deepcopy(store)  # a blocked turn did not happen: its refunds are undone too
        extra_body["thread"] = {"id": f"{settings.prefix}-chat-{conversation_id[:8]}"}
    context = {
        "message": message, "history": history, "conversation_id": conversation_id, "model": model,
        "extra_body": extra_body, "store": store, "snapshot": snapshot, "guarded": bool(choice),
        "started": time.perf_counter(),
    }
    return context, None


def _release(context: dict[str, Any], done: bool) -> None:
    """End of a turn: free the conversation and, when the turn failed, undo its refunds."""
    conversation_id = context["conversation_id"]
    if conversation_id:
        _busy.discard(conversation_id)
        if not done and context["snapshot"] is not None:  # any failed turn did not happen
            _stores[conversation_id] = context["snapshot"]


def _blocked_reply(exc: APIStatusError, context: dict[str, Any]) -> dict[str, Any] | None:
    blocked = _blocked(exc)
    if blocked is None:
        return None
    # The turn did not happen: history stays as the browser sent it (the orders are restored by _release).
    return {
        "blocked": blocked,
        "trace_url": trace_url(blocked["trace_id"]),
        "history": context["history"],
        "model": context["model"],
        "seconds": round(time.perf_counter() - context["started"], 1),
    }


async def post_chat(request: Request) -> JSONResponse:
    """One customer message on top of the history the browser sent back.

    `chat()` blocks on the model calls, so it runs in a worker thread and other requests go on.
    """
    context, error = await _chat_context(request)
    if error is not None:
        return error
    model, message, history = context["model"], context["message"], context["history"]
    steps: list[str] = []
    done = False
    try:
        if model.startswith("agent/"):
            answer, names, trace_id, history, steps = await run_in_threadpool(
                _hosted_turn, model, message, history, context["extra_body"]
            )
            tool_calls = names  # orq ran them: the sub-agents' texts are in each call, other results are in the trace
        else:
            result = await run_in_threadpool(
                chat,
                message,
                history=history,
                store=context["store"],
                client=make_openai_client(),
                model=model,
                identity=settings.identity_id,
                extra_body=context["extra_body"],
            )
            answer, trace_id, history = result.text, result.trace_id, result.messages
            tool_calls = _tool_outcomes(result.messages, result.tool_calls)
        done = True
    except APIStatusError as exc:
        reply = _blocked_reply(exc, context)
        if reply is None:
            return _error(502, f"gateway error: {exc}")
        return JSONResponse(reply)
    except OpenAIError as exc:
        return _error(502, f"gateway error: {exc}")
    finally:
        _release(context, done)
    return JSONResponse(
        {
            "answer": answer,
            "tool_calls": tool_calls,
            "trace_id": trace_id,
            "trace_url": trace_url(trace_id),
            "history": history,
            "steps": steps,
            "model": model,
            "seconds": round(time.perf_counter() - context["started"], 1),
        }
    )


def _sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode()


async def post_chat_stream(request: Request) -> Response:
    """Like /api/chat, as server-sent events: node, step, delta and a final done event.

    Errors before the first event keep the status codes of /api/chat. Errors after it are an
    `error` event. The gateway does not run output guardrails on a stream: the page does not offer
    streaming while a Guardrails choice is on, and a request that asks for both is refused.
    """
    context, error = await _chat_context(request)
    if error is not None:
        return error
    if context["guarded"]:
        _release(context, False)
        return _error(422, "output guardrails do not run on a stream: set Guardrails to Off or turn streaming off")
    if context["model"].startswith("agent/"):
        turn = _stream_turn(context["model"], context["message"], context["history"], context["extra_body"])
    else:
        turn = _stream_local_turn(
            context["model"], context["message"], context["history"], context["store"], context["extra_body"]
        )
    events = iterate_in_threadpool(turn)
    try:  # the first event proves the gateway accepted the request; a block or a bad key is still a plain reply
        first = await anext(events)
    except APIStatusError as exc:
        _release(context, False)
        reply = _blocked_reply(exc, context)
        return JSONResponse(reply) if reply else _error(502, f"gateway error: {exc}")
    except (OpenAIError, StopAsyncIteration) as exc:
        _release(context, False)
        return _error(502, f"gateway error: {exc}")

    async def body():
        done = False
        try:
            yield _sse(first)
            async for event in events:
                if event["type"] == "done":
                    event["seconds"] = round(time.perf_counter() - context["started"], 1)
                    event["model"] = context["model"]
                    done = True
                yield _sse(event)
        except (OpenAIError, httpx.HTTPError) as exc:
            yield _sse({"type": "error", "message": f"gateway error: {exc}"})
        finally:
            _release(context, done)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)


def _static(path):
    return lambda request: FileResponse(path)


app = Starlette(
    routes=[
        Route("/favicon.svg", _static(ROOT / "web" / "favicon.svg")),
        Route("/fonts/kurrent.woff2", _static(FONTS / "ESKlarheitKurrent-Rg.woff2")),
        Route("/fonts/kurrent-medium.woff2", _static(FONTS / "ESKlarheitKurrent-Md.woff2")),
        Route("/fonts/kurrent-semibold.woff2", _static(FONTS / "ESKlarheitKurrent-Smbd.woff2")),
        Route("/fonts/kurrent-mono.woff2", _static(FONTS / "ESKlarheitKurrentMono-Md.woff2")),
        Route("/", index),
        Route("/api/models", get_models),
        Route("/api/backend", get_backend),
        Route("/api/chat", post_chat, methods=["POST"]),
        Route("/api/chat/stream", post_chat_stream, methods=["POST"]),
        Route("/api/agent-graph", get_agent_graph),
    ]
)

if __name__ == "__main__":
    # Restarts on any .py or .env change in the repo (settings are read at import).
    # web/index.html needs no restart: it is read from disk per request, refresh the browser.
    uvicorn.run(
        "app.web:app",
        host="127.0.0.1",
        port=PORT,
        reload=True,
        reload_dirs=[str(ROOT)],
        reload_includes=["*.py", ".env"],
    )
