"""Toqan chat: an agent loop that runs here, every model call through the Toqan Router.

What: one page (`index.html`) and three routes. `GET /api/options` lists the models, the smart
routers, the personas and the scenarios; `POST /api/chat` runs one turn and returns its events as a
JSON list; `POST /api/chat/stream` sends the same events as server-sent events while the turn runs.
Why: a chat you can drive live, where each scenario tags the call (identity + metadata) so a routing
rule, a guardrail, a fallback or a server tool in the `toqan` workspace kicks in, and every answer
links to its trace. Two personas (`personas.py`): a shopper who delegates a purchase, a merchant.
How: `make toqan-chat-ui`. Stateless, so it runs on Vercel as is: the browser sends `history` back.

Events: `step` (a tool call, `running` then `done`), `delta` (answer text), `round` (one model
call: asked, answered, tokens, server tools, trace), `blocked` (a guardrail stopped the call),
`server` (a tool the router ran by itself: its input and result), `error`, `done`.
Wire: the Responses API (`/v3/router/responses`), stateless (`store: false`, every item sent back).
"""

from __future__ import annotations

import functools
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from openai import APIStatusError, OpenAI, OpenAIError
from starlette.applications import Starlette
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from personas import PERSONAS

HERE = Path(__file__).resolve().parent
BASE_URL = os.environ.get("TOQAN_BASE_URL", "https://router.toqan.ai/br").rstrip("/")
WORKSPACE = os.environ.get("TOQAN_WORKSPACE", "toqan")
TRACE_HEADER = "x-orq-trace-id"  # the router's trace header; never shown in the page
MAX_TOOL_ROUNDS = 6
# The page is public: keep it a demo, not a free proxy to the key (the workspace budgets cap the rest).
MAX_MESSAGE_CHARS, MAX_HISTORY_ITEMS, MAX_HISTORY_CHARS = 2000, 150, 250000
HANDOFF = "Não consegui concluir. Vou te passar para uma pessoa da equipe."
APP_TAG = "toqan-router-demo"  # trace name, metadata `app` and thread prefix: how to find the demo's traces

ROUTERS = ["menor-custo", "maxima-qualidade", "equilibrado"]  # smart routers in the `toqan` workspace
FALLBACK_MODEL = "aws/global.anthropic.claude-haiku-4-5-20251001-v1:0"  # Bedrock answers 404: the fallback rule takes over
DEFAULT_MODEL = "aws/us.anthropic.claude-haiku-5-5"
NO_TOOLS = {"aws/google.gemma-3-27b-it", FALLBACK_MODEL}  # gemma answers in text instead of calling tools
MODELS = [  # when the key cannot list models; each called a tool through the router on 11 Nov 2026
    "aws/us.anthropic.claude-haiku-5-5", "aws/global.anthropic.claude-sonnet-5-5", "aws/global.anthropic.claude-opus-5-5",
    "openai/gpt-5.6-luna", "openai/gpt-5.6-sol", "aws/openai.gpt-oss-120b-1:0", "aws/deepseek.v3.2", "aws/moonshotai.kimi-k2.5",
]
# What each scenario does to the call. The rules live in the `toqan` workspace and match on these headers;
# the example messages are per persona (personas.py).
CENARIOS = {
    "livre": {"nome": "Livre", "identity": "produto", "usecase": None,
              "desc": "Sem regra: o modelo escolhido responde."},
    "atendimento": {"nome": "Roteamento 80/20", "identity": "atendimento", "usecase": "atendimento",
                    "desc": "Regra por peso: 80% GPT-OSS, 20% DeepSeek, seja qual for o modelo pedido."},
    # one call, no tools, no history: the same question is the same request, so the cache rule can answer it
    "faq": {"nome": "Cache", "identity": "atendimento", "usecase": "perguntas-frequentes", "faq": True,
            "desc": "Regra de cache de 1 hora: a mesma pergunta de novo volta do cache, sem chamar o modelo."},
    "firewall": {"nome": "Firewall de IA", "identity": "atendimento", "usecase": "chat-com-cliente", "guarded": True,
                 "desc": "Regra de guardrail: bloqueia cartão, CPF, injeção de prompt e promessa fora da política."},
    "diretoria": {"nome": "VIP · sempre Opus", "identity": "diretoria", "usecase": None,
                  "desc": "Regra por identidade: a conta VIP sempre recebe o Claude Opus."},
    "fallback": {"nome": "Fallback", "identity": "produto", "usecase": None, "model": FALLBACK_MODEL,
                 "desc": "O Claude Haiku 4.5 no Bedrock falha (404) e a regra de fallback responde com o GPT-OSS."},
    # server tools run inside the router; they need a provider/model (a smart router gets 403 license_provider_disabled).
    # orq:web_search and orq:web_fetch answered "no responders available" in BR on 11 Nov 2026, so they are left out.
    "ferramentas": {"nome": "Ferramentas do router", "identity": "produto", "usecase": None,
                    "server_tools": [{"type": "orq:code_interpreter"},
                                     {"type": "orq:advisor", "model": "aws/global.anthropic.claude-opus-5-5", "max_uses": 1},
                                     {"type": "orq:datetime", "timezone": "America/Sao_Paulo"}],
                    "hint": "Ferramentas do router: para qualquer conta, rode Python com `orq_code_interpreter`; quando pedirem conselho ou "
                            "a decisão envolver dinheiro alto, consulte `orq_advisor` antes de responder; para data e hora, use `orq_datetime`.",
                    "desc": "O router roda ferramentas sozinho: Python num sandbox, um conselheiro (Claude Opus) e a data de hoje."},
}


def request_problem(message: str, history: list, model: str) -> str | None:
    """Why a public request is refused, or None: unknown model, oversized message or history."""
    allowed = {*workspace_models(), *(f"toqan@orq/{r}" for r in ROUTERS), FALLBACK_MODEL}
    if model not in allowed:
        return "modelo fora da lista da demo"
    if len(message) > MAX_MESSAGE_CHARS:
        return f"mensagem acima de {MAX_MESSAGE_CHARS} caracteres"
    if len(history) > MAX_HISTORY_ITEMS or len(json.dumps(history, ensure_ascii=False)) > MAX_HISTORY_CHARS:
        return "conversa longa demais: comece uma nova conversa"
    return None


def faq_instructions(persona: dict) -> str:
    return ("Responda à pergunta frequente em até 3 frases, em português do Brasil, só com base nestas políticas:\n"
            + "\n".join(f"- {tema}: {texto}" for tema, texto in persona["politicas"].items()))


def api_key() -> str:
    key = os.environ.get("TOQAN_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TOQAN_API_KEY não está definida (veja toqan-chat/.env.example).")
    return key


def trace_url(trace_id: str | None) -> str | None:
    return f"{BASE_URL}/{WORKSPACE}/traces/(trace:{trace_id})" if trace_id else None


@functools.cache  # ponytail: read once per process; restart (or a new Vercel instance) to pick up new models
def workspace_models() -> list[str]:
    """Enabled chat models of the workspace that call tools; MODELS when the key may not list them."""
    try:
        r = httpx.get(f"{BASE_URL}/v2/models", headers={"Authorization": f"Bearer {api_key()}"}, timeout=15)
        r.raise_for_status()
        ids = [f"{m['provider']}/{m['model_id']}" for m in r.json()
               if m.get("enabled") and m.get("model_type") == "chat" and m.get("provider") != "orq"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError):
        return MODELS
    return [i for i in ids if i not in NO_TOOLS] or MODELS


# ---------------------------------------------------------------- the agent loop

def _usage(usage) -> dict[str, Any]:
    """Tokens, cost (US$), whether the cache answered, and the router's server-tool counters."""
    extra = getattr(usage, "model_extra", None) or {}
    tokens = getattr(usage, "total_tokens", None)
    cost = sum(v for v in (extra.get("input_cost"), extra.get("output_cost")) if isinstance(v, (int, float)))
    # a cache hit comes back with zero tokens and no cost (11 Nov 2026)
    return {"tokens": tokens, "cost": round(cost, 6), "cached": tokens == 0, "server_tools": extra.get("server_tool_use") or {}}


def _budget(headers) -> dict[str, Any] | None:
    """The key's budget and rate limit, from the router's x-ratelimit-* headers (absent without a budget)."""
    try:
        return {"limit": float(headers["x-ratelimit-limit-cost"]), "remaining": float(headers["x-ratelimit-remaining-cost"]),
                "rpm": int(headers["x-ratelimit-limit"]), "rpm_remaining": int(headers["x-ratelimit-remaining"])}
    except (KeyError, TypeError, ValueError):
        return None


def _clip(value: Any, limit: int = 1500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


def _server_events(output: list) -> list[dict]:
    """The server tools the router ran inside the call (`orq:code_interpreter`, `orq:advisor`…): what each got and gave back.

    The `orq:*` item holds the result; its arguments sit on the twin `orq_*` function_call with the same call_id
    (a streamed `orq:*` item comes without them).
    """
    get = lambda item, k: getattr(item, k, None) or (item.model_extra or {}).get(k)  # the SDK keeps known fields as attributes
    args = {get(i, "call_id"): get(i, "arguments") for i in output if i.type == "function_call"}
    return [{"type": "server", "id": get(i, "call_id"), "tool": i.type,
             "input": _clip(get(i, "arguments") or args.get(get(i, "call_id")) or ""), "result": _clip(get(i, "result") or "")}
            for i in output if i.type.startswith("orq:")]


def _ours(item) -> bool:
    """A function call our code must run (the router runs its own `orq_*` ones and reports them as `orq:*` items)."""
    return item.type == "function_call" and not item.name.startswith("orq_")


def _round(client: OpenAI, model: str, instructions: str, items: list, headers: dict, extra: dict, stream: bool, tools: list):
    """One Responses call. Yields `delta`, `step running` and `server` events, then returns
    (text, calls, output items, answered model, usage + budget, trace_id)."""
    raw = client.responses.with_raw_response.create(
        model=model, instructions=instructions, input=items, store=False, stream=stream,
        extra_headers=headers, extra_body=extra, **({"tools": tools} if tools else {}),
    )
    trace_id = raw.headers.get(TRACE_HEADER)
    if stream:
        resp = None
        for ev in raw.parse():
            item = getattr(ev, "item", None)
            if ev.type == "response.output_text.delta":
                yield {"type": "delta", "text": ev.delta}
            elif ev.type == "response.output_item.added" and _ours(item):
                yield {"type": "step", "id": item.call_id, "tool": item.name, "state": "running"}
            elif ev.type == "response.completed":
                resp = ev.response
        if resp is None:
            raise OpenAIError("o stream terminou sem response.completed")
    else:  # a guarded call: output guardrails only run on a full response
        resp = raw.parse()
    yield from _server_events(resp.output)
    text = "".join(c.text for i in resp.output if i.type == "message" for c in i.content if getattr(c, "type", "") == "output_text")
    if text and not stream:
        yield {"type": "delta", "text": text}
    calls = [{"id": i.call_id, "name": i.name, "arguments": i.arguments or "{}"} for i in resp.output if _ours(i)]
    # every output item goes back next round, reasoning and orq:* results included: without them the
    # model runs a server tool again (11 Nov 2026)
    output = [i.model_dump(exclude_none=True) for i in resp.output]
    return text, calls, output, resp.model, {**_usage(resp.usage), "budget": _budget(raw.headers)}, trace_id


ITEM_ROLES, ITEM_TYPES = ("user", "assistant"), ("message", "function_call", "function_call_output", "reasoning")


def _history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Responses items the browser sent back, minus anything that is not one."""
    return [m for m in history if m.get("role") in ITEM_ROLES or m.get("type") in ITEM_TYPES or str(m.get("type", "")).startswith("orq:")]


def run_turn(client: OpenAI, model: str, message: str, history: list[dict[str, Any]], cenario: str, stream: bool,
             persona: str = "comprador", conversation: str = ""):
    """One message on top of `history`: model, tools, model… as UI events (a sync generator)."""
    scen, who = CENARIOS[cenario], PERSONAS[persona]
    model = scen.get("model") or model
    if scen.get("server_tools") and model.startswith("toqan@"):
        model = DEFAULT_MODEL  # smart routers do not take server tools
    tools = [] if scen.get("faq") else [{"type": "function", **t["function"]} for t in who["tools"]] + scen.get("server_tools", [])
    instructions = faq_instructions(who) if scen.get("faq") else who["instructions"] + ("\n" + scen["hint"] if scen.get("hint") else "")
    # app / persona / cenario metadata: filter the demo's traces in Toqan (Traces → metadata app = toqan-router-demo)
    headers = {"X-Toqan-Identity-Id": scen["identity"], "X-Toqan-Metadata-App": APP_TAG,
               "X-Toqan-Metadata-Cenario": cenario, "X-Toqan-Metadata-Persona": persona}
    if scen["usecase"]:
        headers["X-Toqan-Metadata-Usecase"] = scen["usecase"]
    extra: dict[str, Any] = {"name": APP_TAG}  # the trace name, instead of chat.aws
    if conversation and not scen.get("faq"):  # the FAQ call stays the same across conversations, so the cache can answer
        extra["thread"] = {"id": f"{APP_TAG}-{conversation[:12]}"}  # one conversation = one thread in Toqan
    prior = _history(history)
    turn = [{"role": "user", "content": message}] if scen.get("faq") else [*prior, {"role": "user", "content": message}]
    answer = ""
    for n in range(1, MAX_TOOL_ROUNDS + 2):  # the last round is the answer, not a tool call
        started = time.perf_counter()
        try:
            text, calls, output, answered, usage, trace_id = yield from _round(
                client, model, instructions, turn, headers, extra, stream, tools)
        except APIStatusError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            trace_id = exc.response.headers.get(TRACE_HEADER)
            if body.get("code") == "guardrail_error":  # the turn did not happen: the browser keeps its history
                failures = [{"stage": f.get("stage"), "reason": f.get("reason")} for f in body.get("failures") or []]
                yield {"type": "blocked", "failures": failures, "trace_url": trace_url(trace_id)}
            else:
                yield {"type": "error", "message": str(body.get("message") or exc)[:400], "trace_url": trace_url(trace_id)}
            return
        except OpenAIError as exc:
            yield {"type": "error", "message": str(exc)[:400], "trace_url": None}
            return
        yield {"type": "round", "n": n, "asked": model, "answered": answered, **usage,
               "seconds": round(time.perf_counter() - started, 1), "trace_url": trace_url(trace_id)}
        turn.extend(output)
        answer = text or answer
        if not calls:
            break
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
            except ValueError:
                args = {}
            result = who["dispatch"](c["name"], args if isinstance(args, dict) else {})
            turn.append({"type": "function_call_output", "call_id": c["id"], "output": json.dumps(result, ensure_ascii=False)})
            yield {"type": "step", "id": c["id"], "tool": c["name"], "state": "done", "input": c["arguments"],
                   "ok": result.get("ok"), "error": result.get("error")}
    else:  # out of rounds
        turn.append({"role": "assistant", "content": HANDOFF})
        answer = HANDOFF
        yield {"type": "delta", "text": HANDOFF}
    if scen.get("faq"):  # the conversation keeps going around the stateless FAQ call
        turn = [*prior, *turn]
    yield {"type": "done", "answer": answer, "history": turn}


# ---------------------------------------------------------------- HTTP

def _public(scen: dict) -> dict:
    return {k: v for k, v in scen.items() if k not in ("identity", "usecase")} | {"server_tools": bool(scen.get("server_tools"))}


async def options(request: Request) -> JSONResponse:
    models = await run_in_threadpool(workspace_models)
    return JSONResponse({
        "default": DEFAULT_MODEL if DEFAULT_MODEL in models else models[0],
        "routers": [{"id": f"toqan@orq/{r}", "label": r} for r in ROUTERS],
        "models": models,
        "traces_url": f"{BASE_URL}/{WORKSPACE}/traces?traces_q={APP_TAG}&traces_range=86400000",  # every trace of the demo, last 24 h
        "cenarios": [{"id": k, **_public(v)} for k, v in CENARIOS.items()],
        "personas": {pid: {"nome": p["nome"], "welcome": p["welcome"], "rail": p["rail"], "exemplos": p["exemplos"]}
                     for pid, p in PERSONAS.items()},
    })


async def _turn(request: Request, stream: bool):
    """Validated (generator, None) or (None, error reply)."""
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return None, JSONResponse({"detail": "o corpo deve ser JSON"}, status_code=400)
    message, history = body.get("message"), body.get("history") or []
    model, cenario, persona = body.get("model") or DEFAULT_MODEL, body.get("cenario") or "livre", body.get("persona") or "comprador"
    conversation = "".join(ch for ch in str(body.get("conversation") or "") if ch.isalnum())[:32]
    if not isinstance(message, str) or not message.strip() or not isinstance(history, list) or not isinstance(model, str) \
            or cenario not in CENARIOS or persona not in PERSONAS or not all(isinstance(m, dict) for m in history):
        return None, JSONResponse({"detail": "esperado {message, history: list, model, cenario, persona}"}, status_code=422)
    problem = await run_in_threadpool(request_problem, message, history, model)
    if problem:
        return None, JSONResponse({"detail": problem}, status_code=422)
    if stream and CENARIOS[cenario].get("guarded"):
        return None, JSONResponse({"detail": "guardrail de saída não roda em stream: use o modo Completa"}, status_code=422)
    try:
        client = OpenAI(api_key=api_key(), base_url=f"{BASE_URL}/v3/router")
    except RuntimeError as exc:
        return None, JSONResponse({"detail": str(exc)}, status_code=500)
    # The router always gets a stream, except under the firewall (output guardrails need a full response):
    # on 11 Nov 2026 Bedrock open models (DeepSeek, GPT-OSS, Kimi) answered full responses with tool arguments "{}",
    # on chat/completions and on Responses alike.
    guarded = CENARIOS[cenario].get("guarded")
    return run_turn(client, model, message, history, cenario, stream=not guarded, persona=persona, conversation=conversation), None


async def chat(request: Request) -> Response:
    """The whole turn as one list of events (the page's "Completa" mode, and the firewall scenario)."""
    turn, error = await _turn(request, stream=False)
    return error or JSONResponse(await run_in_threadpool(list, turn))


async def chat_stream(request: Request) -> Response:
    turn, error = await _turn(request, stream=True)
    if error:
        return error

    async def sse():
        async for event in iterate_in_threadpool(turn):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app = Starlette(routes=[
    Route("/", lambda request: FileResponse(HERE / "index.html")),
    Route("/qr.svg", lambda request: FileResponse(HERE / "qr.svg", media_type="image/svg+xml")),  # this demo's public URL
    Route("/api/options", options),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/chat/stream", chat_stream, methods=["POST"]),
])
