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
`error`, `done`.
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
HANDOFF = "Não consegui concluir. Vou te passar para uma pessoa da equipe."

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
                    "desc": "O router roda ferramentas sozinho: Python num sandbox, um conselheiro (Claude Opus) e a data de hoje."},
}


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
    """Tokens and the router's server-tool counters (`usage.server_tool_use`, e.g. {"advisor_requests": 1})."""
    extra = getattr(usage, "model_extra", None) or {}
    return {"tokens": getattr(usage, "total_tokens", None), "server_tools": extra.get("server_tool_use") or {}}


def _round(client: OpenAI, model: str, messages: list, headers: dict, stream: bool, tools: list):
    """One model call. Yields `delta` / `step running` events, then returns (text, calls, answered, usage, trace_id)."""
    raw = client.chat.completions.with_raw_response.create(
        model=model, messages=messages, reasoning_effort="none",  # GPT-5.x refuses tools without it
        extra_headers=headers, stream=stream, **({"tools": tools} if tools else {}),
        **({"stream_options": {"include_usage": True}} if stream else {}),
    )
    trace_id = raw.headers.get(TRACE_HEADER)
    if not stream:  # a guarded call: output guardrails only run on a full response
        resp = raw.parse()
        msg = resp.choices[0].message
        if msg.content:
            yield {"type": "delta", "text": msg.content}
        calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"} for c in msg.tool_calls or []]
        return msg.content or "", calls, resp.model, _usage(resp.usage), trace_id
    text, calls, answered, usage = "", {}, None, {"tokens": None, "server_tools": {}}
    for chunk in raw.parse():
        answered = chunk.model or answered
        usage = _usage(chunk.usage) if chunk.usage else usage
        for choice in chunk.choices:
            if choice.delta.content:
                text += choice.delta.content
                yield {"type": "delta", "text": choice.delta.content}
            for tc in choice.delta.tool_calls or []:  # arguments arrive in pieces, keyed by index
                call = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                call["id"] = tc.id or call["id"]
                if tc.function and tc.function.name:
                    call["name"] += tc.function.name
                    yield {"type": "step", "id": call["id"], "tool": call["name"], "state": "running"}
                if tc.function and tc.function.arguments:
                    call["arguments"] += tc.function.arguments
    return text, list(calls.values()), answered, usage, trace_id


def run_turn(client: OpenAI, model: str, message: str, history: list[dict[str, Any]], cenario: str, stream: bool,
             persona: str = "comprador"):
    """One message on top of `history`: model, tools, model… as UI events (a sync generator)."""
    scen, who = CENARIOS[cenario], PERSONAS[persona]
    model = scen.get("model") or model
    if scen.get("server_tools") and model.startswith("toqan@"):
        model = DEFAULT_MODEL  # smart routers do not take server tools
    tools = [] if scen.get("faq") else who["tools"] + scen.get("server_tools", [])
    instructions = faq_instructions(who) if scen.get("faq") else who["instructions"]
    headers = {"X-Toqan-Identity-Id": scen["identity"], "X-Toqan-Metadata-Cenario": cenario, "X-Toqan-Metadata-Persona": persona}
    if scen["usecase"]:
        headers["X-Toqan-Metadata-Usecase"] = scen["usecase"]
    prior = [m for m in history if m.get("role") in ("user", "assistant", "tool")]
    turn = [{"role": "user", "content": message}] if scen.get("faq") else [*prior, {"role": "user", "content": message}]
    answer = ""
    for n in range(1, MAX_TOOL_ROUNDS + 2):  # the last round is the answer, not a tool call
        started = time.perf_counter()
        try:
            text, calls, answered, usage, trace_id = yield from _round(
                client, model, [{"role": "system", "content": instructions}, *turn], headers, stream, tools)
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
        assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            assistant["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]
        turn.append(assistant)
        answer = text or answer
        if not calls:
            break
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
            except ValueError:
                args = {}
            result = who["dispatch"](c["name"], args if isinstance(args, dict) else {})
            turn.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, ensure_ascii=False)})
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
    if not isinstance(message, str) or not message.strip() or not isinstance(history, list) or not isinstance(model, str) \
            or cenario not in CENARIOS or persona not in PERSONAS or not all(isinstance(m, dict) for m in history):
        return None, JSONResponse({"detail": "esperado {message, history: list, model, cenario, persona}"}, status_code=422)
    if stream and CENARIOS[cenario].get("guarded"):
        return None, JSONResponse({"detail": "guardrail de saída não roda em stream: use o modo Completa"}, status_code=422)
    try:
        client = OpenAI(api_key=api_key(), base_url=f"{BASE_URL}/v3/router")
    except RuntimeError as exc:
        return None, JSONResponse({"detail": str(exc)}, status_code=500)
    # The router always gets a stream, except under the firewall (output guardrails need a full response):
    # on 11 Nov 2026 Bedrock open models (DeepSeek, GPT-OSS, Kimi) answered full responses with tool arguments "{}".
    guarded = CENARIOS[cenario].get("guarded")
    return run_turn(client, model, message, history, cenario, stream=not guarded, persona=persona), None


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
    Route("/api/options", options),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/chat/stream", chat_stream, methods=["POST"]),
])
