"""make web: talk to the refund agent in a browser, one link to the trace per answer.

What: two routes. `GET /` serves `web/index.html`; `POST /api/chat` runs one turn of the same
`chat()` every module uses and returns the answer, the tools called, the trace id and a Studio
link to that trace.
Why: a transcript in a browser is easier to read than a terminal, and the trace link closes the
loop from "what did the agent say" to "what did it do".
How: `make web` (or `uv run python -m app.web`), then open http://127.0.0.1:8002. Stateless like
the rest of the repo (Factor 12): the browser sends back the full `history` it got last time. The
one thing kept server-side is an `OrderStore` per `conversation_id`, so a refund issued in turn 1
is still refunded in turn 2; it lives in memory and resets when the server restarts.

Request:  {"message": str, "history": [...], "conversation_id": str}  (history and id optional)
Response: {"answer", "tool_calls", "trace_id", "trace_url", "history"}
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import uvicorn
from openai import OpenAIError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from app.refund_agent.agent import chat
from app.refund_agent.client import make_openai_client
from app.refund_agent.config import ROOT, settings
from app.refund_agent.tools import OrderStore

INDEX_HTML = ROOT / "web" / "index.html"
PORT = 8002
_stores: dict[str, OrderStore] = {}  # conversation_id -> its orders; in memory, per process


def trace_url(trace_id: str | None) -> str | None:
    """Studio deep link to one trace; the Traces page when ORQ_WORKSPACE is not set."""
    if not trace_id:
        return None
    if not settings.workspace:
        return f"{settings.base_url}/traces"
    query = quote(f"trace_id:is:{trace_id}", safe="")
    return f"{settings.base_url}/{quote(settings.workspace, safe='')}/traces?query={query}"


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def index(request: Request) -> FileResponse:
    return FileResponse(INDEX_HTML)


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
    if not isinstance(message, str) or not message.strip() or not isinstance(history, list):
        return _error(422, "expected {message: non-empty string, history: list}")

    store = OrderStore()
    extra_body: dict[str, Any] = {"name": "refund-chat"}
    if conversation_id:
        store = _stores.setdefault(conversation_id, store)
        extra_body["thread"] = {"id": f"{settings.prefix}-chat-{conversation_id[:8]}"}
    try:
        result = await run_in_threadpool(
            chat,
            message,
            history=history,
            store=store,
            client=make_openai_client(),
            identity=settings.identity_id,
            extra_body=extra_body,
        )
    except OpenAIError as exc:
        return _error(502, f"gateway error: {exc}")
    return JSONResponse(
        {
            "answer": result.text,
            "tool_calls": result.tool_calls,
            "trace_id": result.trace_id,
            "trace_url": trace_url(result.trace_id),
            "history": result.messages,
        }
    )


app = Starlette(routes=[Route("/", index), Route("/api/chat", post_chat, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
