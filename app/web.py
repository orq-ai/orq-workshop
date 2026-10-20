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

import time
from typing import Any
from urllib.parse import quote

import httpx
import uvicorn
from openai import OpenAIError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from app.refund_agent.agent import IDENTITY_HEADER, TRACE_HEADER, chat
from app.refund_agent.client import make_openai_client, make_orq
from app.refund_agent.config import ROOT, settings
from app.refund_agent import tools
from app.refund_agent.tools import OrderStore

INDEX_HTML = ROOT / "web" / "index.html"
PORT = 8002
FONTS = ROOT / "docs" / "stylesheets" / "fonts"  # the page uses the docs site's typeface
ORDER_FIELDS = ("id", "item", "amount", "delivered_days_ago", "refunded")  # never owner_id or notes
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
    if not settings.workspace:
        return f"{settings.base_url}/traces"
    # Studio route: /traces/(trace:<id>), optionally //span:<id>; we only have the trace id
    return f"{settings.base_url}/{quote(settings.workspace, safe='')}/traces/(trace:{quote(trace_id, safe='')})"


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
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError):
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
    except Exception:  # noqa: BLE001  not seeded yet, or not readable: leave it out of the picker
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
    if not settings.api_key:
        return _error(500, "ORQ_API_KEY is empty. Copy .env.example to .env and fill it.")
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
    if conversation_id:
        store = _stores.setdefault(conversation_id, store)
        extra_body["thread"] = {"id": f"{settings.prefix}-chat-{conversation_id[:8]}"}
    started = time.perf_counter()
    try:
        if model.startswith("agent/"):
            answer, tool_calls, trace_id, history = await run_in_threadpool(
                _hosted_turn, model, message, history, extra_body
            )
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
            answer, tool_calls, trace_id, history = (
                result.text,
                result.tool_calls,
                result.trace_id,
                result.messages,
            )
    except OpenAIError as exc:
        return _error(502, f"gateway error: {exc}")
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
        Route("/favicon.svg", _static(ROOT / "docs" / "assets" / "orq-favicon.svg")),
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
