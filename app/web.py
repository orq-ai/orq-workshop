"""make web: talk to the refund agent in a browser, one link to the trace per answer.

What: two routes. `GET /` serves `web/index.html`; `POST /api/chat` runs one turn of the same
`chat()` every module uses and returns the answer, the tools called, the trace id and a Studio
link to that trace.
Why: a transcript in a browser is easier to read than a terminal, and the trace link closes the
loop from "what did the agent say" to "what did it do".
How: `make web`, then open http://127.0.0.1:8002. Stateless like the rest of the repo (Factor 12):
the browser sends back the full `history` it got last time. The one thing kept server-side is an
`OrderStore` per `conversation_id`, so a refund issued in turn 1 is still refunded in turn 2; it
lives in memory and resets when the server restarts.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.refund_agent.agent import chat
from app.refund_agent.client import make_openai_client
from app.refund_agent.config import ROOT, settings
from app.refund_agent.tools import OrderStore

INDEX_HTML = ROOT / "web" / "index.html"

app = FastAPI(title="Refund agent chat")
_stores: dict[str, OrderStore] = {}  # conversation_id -> its orders; in memory, per process


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)  # `history` from the last reply
    conversation_id: str = ""  # the browser mints one per conversation; also the trace thread


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[str]
    trace_id: str | None
    trace_url: str | None
    history: list[dict[str, Any]]


def trace_url(trace_id: str | None) -> str | None:
    """Studio deep link to one trace; the Traces page when ORQ_WORKSPACE is not set."""
    if not trace_id:
        return None
    if not settings.workspace:
        return f"{settings.base_url}/traces"
    query = quote(f"trace_id:is:{trace_id}", safe="")
    return f"{settings.base_url}/{quote(settings.workspace, safe='')}/traces?query={query}"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.post("/api/chat")
def post_chat(req: ChatRequest) -> ChatResponse:
    """One customer message on top of the history the browser sent back."""
    if not settings.api_key:
        raise HTTPException(500, "ORQ_API_KEY is empty. Copy .env.example to .env and fill it.")
    store = OrderStore()
    extra_body: dict[str, Any] = {"name": "refund-chat"}
    if req.conversation_id:
        store = _stores.setdefault(req.conversation_id, store)
        extra_body["thread"] = {"id": f"{settings.prefix}-chat-{req.conversation_id[:8]}"}
    try:
        result = chat(
            req.message,
            history=req.history,
            store=store,
            client=make_openai_client(),
            identity=settings.identity_id,
            extra_body=extra_body,
        )
    except OpenAIError as exc:
        raise HTTPException(502, f"gateway error: {exc}") from exc
    return ChatResponse(
        answer=result.text,
        tool_calls=result.tool_calls,
        trace_id=result.trace_id,
        trace_url=trace_url(result.trace_id),
        history=result.messages,
    )
