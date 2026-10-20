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

import copy
import json
import time
from typing import Any
from urllib.parse import quote

import httpx
import uvicorn
from openai import APIStatusError, OpenAIError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from app.refund_agent import tools
from app.refund_agent.agent import IDENTITY_HEADER, TRACE_HEADER, chat
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


async def get_backend(request: Request) -> JSONResponse:
    return JSONResponse(backend_view())


async def get_models(request: Request) -> JSONResponse:
    """The picker's options: the configured MODEL first and selected, then the hosted agent if seeded."""
    models = await run_in_threadpool(_workspace_models)
    agents = [hosted_agent()] if await run_in_threadpool(_hosted_agent_exists) else []
    return JSONResponse(
        {
            "default": settings.model,
            "models": [settings.model, *(m for m in models if m != settings.model)],
            "agents": agents,
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


def _hosted_turn(
    model: str, message: str, history: list[dict[str, Any]], extra_body: dict[str, Any]
) -> tuple[str, list[str], str | None, list[dict[str, Any]]]:
    """One turn on an agent that lives in orq: one Responses call, orq runs the loop and the tools.

    The agent has its own instructions and tools, so it gets only the text of the conversation
    (user and assistant messages), not our system prompt or our tool items. The history we return
    is the browser's plus this exchange, so the conversation can switch back to a plain model.
    """
    transcript = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]
    raw = make_openai_client().responses.with_raw_response.create(
        model=model,
        input=[*transcript, {"role": "user", "content": message}],
        extra_body=extra_body,
        extra_headers={IDENTITY_HEADER: settings.identity_id},
    )
    response = raw.parse()
    answer = response.output_text
    tool_calls = [item.name for item in response.output if item.type == "function_call"]
    turn = [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    return answer, tool_calls, raw.headers.get(TRACE_HEADER), [*history, *turn]


async def post_chat(request: Request) -> JSONResponse:
    """One customer message on top of the history the browser sent back.

    `chat()` blocks on the model calls, so it runs in a worker thread and other requests go on.
    """
    try:
        await run_in_threadpool(settings.bearer)  # API key, else the `orq auth login` session
    except SystemExit as exc:
        return _error(500, str(exc))
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "body must be JSON")
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
        return _error(422, "expected {message: non-empty string, history: list, model: string}")

    store = OrderStore()
    extra_body: dict[str, Any] = {"name": "refund-chat"}
    choice = {True: "both", None: "", False: ""}.get(body.get("guardrails"), body.get("guardrails"))
    if choice and choice not in CHAT_CHANNELS:
        return _error(422, f"guardrails must be one of {sorted(CHAT_CHANNELS)} or empty")
    if choice:
        # Responses ignores request-level `guardrails`; a rule matching this tag guards the call.
        # `make seed` creates the rules; rules are admin-only, so a workshop key cannot read them back.
        extra_body["metadata"] = {"channel": CHAT_CHANNELS[choice]}
    snapshot = None
    if conversation_id:
        if conversation_id in _busy:
            return _error(409, "this conversation is still answering the previous message")
        _busy.add(conversation_id)
        store = _stores.setdefault(conversation_id, store)
        snapshot = copy.deepcopy(store)  # a blocked turn did not happen: its refunds are undone too
        extra_body["thread"] = {"id": f"{settings.prefix}-chat-{conversation_id[:8]}"}
    started = time.perf_counter()
    done = False
    try:
        if model.startswith("agent/"):
            answer, names, trace_id, history = await run_in_threadpool(
                _hosted_turn, model, message, history, extra_body
            )
            tool_calls = [{"name": n, "ok": None, "error": None} for n in names]  # orq ran them: no results here
        else:
            result = await run_in_threadpool(
                chat,
                message,
                history=history,
                store=store,
                client=make_openai_client(),
                model=model,
                identity=settings.identity_id,
                extra_body=extra_body,
            )
            answer, trace_id, history = result.text, result.trace_id, result.messages
            tool_calls = _tool_outcomes(result.messages, result.tool_calls)
        done = True
    except APIStatusError as exc:
        blocked = _blocked(exc)
        if blocked is None:
            return _error(502, f"gateway error: {exc}")
        # The turn did not happen: history stays as the browser sent it (the orders are restored below).
        return JSONResponse(
            {
                "blocked": blocked,
                "trace_url": trace_url(blocked["trace_id"]),
                "history": history,
                "model": model,
                "seconds": round(time.perf_counter() - started, 1),
            }
        )
    except OpenAIError as exc:
        return _error(502, f"gateway error: {exc}")
    finally:
        if conversation_id:
            _busy.discard(conversation_id)
            if not done and snapshot is not None:  # any failed turn did not happen: undo its refunds too
                _stores[conversation_id] = snapshot
    return JSONResponse(
        {
            "answer": answer,
            "tool_calls": tool_calls,
            "trace_id": trace_id,
            "trace_url": trace_url(trace_id),
            "history": history,
            "model": model,
            "seconds": round(time.perf_counter() - started, 1),
        }
    )


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
