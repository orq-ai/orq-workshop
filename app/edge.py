"""The edge: the one small HTTP service orq calls back into during the workshop.

Two contracts in one process, so one tunnel (or one hosted instance) serves both:

    POST /search             module 09, external knowledge base (registered as api_url): {query, top_k, threshold, ...}
                             -> {"matches": [{id, text, metadata, scores}]}, keyword scoring over app/data/kb
    POST /<prefix>           module 14, webhook delivery for one participant (WS_PREFIX), HMAC verified
    GET  /<prefix>/events    what arrived for that prefix, newest last
    GET  /events             everything, all prefixes
    GET  /health

Auth is one shared secret, WS_WEBHOOK_SECRET: orq signs webhook bodies with it (`X-Orq-Signature`,
hex HMAC-SHA256) and sends it as `Authorization: Bearer` on /search (the knowledge base's api_key).

    uv run python -m app.edge                 # http://127.0.0.1:8001
    docker build -t orq-edge . && docker run -p 8001:8001 -e WS_WEBHOOK_SECRET=... orq-edge

orq cloud has to reach it: a tunnel (npx localtunnel --port 8001) or one hosted instance the
whole room shares, each participant on their own /<prefix>. ponytail: in-memory events, one
process; a file or a DB if it ever has to survive a restart. Reads only os.environ so the Docker
image needs nothing from the rest of the app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

try:  # local runs read .env; the Docker image has no dotenv and takes the environment as is
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

SECRET = os.environ.get("WS_WEBHOOK_SECRET", "")  # empty: accept everything, verify nothing
KB_DIR = Path(os.environ.get("WS_KB_DIR", Path(__file__).parent / "data" / "kb"))
DOCS = {path.stem: path.read_text() for path in sorted(KB_DIR.glob("*.md"))}  # topic -> policy text
EVENTS: list[dict] = []
MAX_EVENTS = 500  # in-memory only: keep the newest ones so a busy room cannot grow it forever
MIN_WORD_LENGTH = 4  # shorter words (the, and, for) match every policy file and flatten the scores


# ------------------------------------------------------------------ module 09: external knowledge base

def kb_search(query: str, top_k: int = 3, threshold: float = 0.0) -> list[dict]:
    """Keyword overlap per policy file, scores in 0..1 as the contract requires.

    The score is the share of the query's words found in the file. Good enough to show the
    contract; a real external KB would put a vector search behind the same shape.
    """
    words = {word for word in re.findall(r"[a-z]+", query.lower()) if len(word) >= MIN_WORD_LENGTH}
    scored = []
    for topic, text in DOCS.items():
        hits = sum(1 for word in words if word in text.lower())
        score = round(hits / max(1, len(words)), 3)
        if score > threshold:
            scored.append(
                {
                    "id": f"ext_{topic}",
                    "text": text,
                    "metadata": {"topic": topic},
                    "scores": {"search_score": score},
                }
            )
    return sorted(scored, key=lambda match: -match["scores"]["search_score"])[:top_k]


async def search(request: Request) -> JSONResponse:
    """POST /search: check the Bearer secret orq sends as the KB's api_key, then score the query."""
    if SECRET and request.headers.get("authorization") != f"Bearer {SECRET}":
        return JSONResponse({"error": "bad bearer token"}, status_code=401)
    body = await request.json()
    matches = kb_search(
        body.get("query", ""),
        int(body.get("top_k") or 3),
        float(body.get("threshold") or 0.0),
    )
    print(f"search   {body.get('query', '')[:50]!r:52} -> {[match['id'] for match in matches]}", flush=True)
    return JSONResponse({"matches": matches})


# ------------------------------------------------------------------ module 14: webhook receiver

async def receive(request: Request) -> JSONResponse:
    """POST /<prefix>: store one webhook delivery and whether its HMAC signature checks out.

    The signature is computed over the raw body bytes, so read them before parsing JSON.
    `signature_valid` is None when no secret is configured (nothing to verify against).
    A bad signature is recorded, not rejected: the event log is where learners see the mismatch.
    """
    prefix = request.path_params.get("prefix", "default")
    body = await request.body()
    signature_valid: bool | None = None
    if SECRET:
        expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        signature_valid = hmac.compare_digest(expected, request.headers.get("x-orq-signature", ""))
    event = json.loads(body or b"{}")
    EVENTS.append(
        {
            "prefix": prefix,
            "type": event.get("type"),
            "id": event.get("id"),
            "created": event.get("created"),
            "signature_valid": signature_valid,
            "data": event.get("data"),
        }
    )
    del EVENTS[:-MAX_EVENTS]
    print(f"{prefix:<10} {event.get('type')!s:<22} {event.get('id')} signature_valid={signature_valid}", flush=True)
    return JSONResponse({"ok": True})


async def events(request: Request) -> JSONResponse:
    """GET /events or /<prefix>/events: what arrived, newest last, optionally for one participant."""
    prefix = request.path_params.get("prefix")
    return JSONResponse({"events": [event for event in EVENTS if not prefix or event["prefix"] == prefix]})


async def health(request: Request) -> JSONResponse:
    """GET /health: is the secret set, how many events are held, which policy files were loaded."""
    return JSONResponse({"ok": True, "verifying": bool(SECRET), "events": len(EVENTS), "kb_docs": sorted(DOCS)})


# Route order matters: the literal paths come before the catch-all /{prefix}.
app = Starlette(
    routes=[
        Route("/search", search, methods=["POST"]),
        Route("/health", health),
        Route("/events", events),
        Route("/{prefix}/events", events),
        Route("/{prefix}", receive, methods=["POST"]),
        Route("/", receive, methods=["POST"]),
    ]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8001")))
