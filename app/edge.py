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

SECRET = os.environ.get("WS_WEBHOOK_SECRET", "")
KB_DIR = Path(os.environ.get("WS_KB_DIR", Path(__file__).parent / "data" / "kb"))
DOCS = {p.stem: p.read_text() for p in sorted(KB_DIR.glob("*.md"))}
EVENTS: list[dict] = []


# ------------------------------------------------------------------ module 09: external knowledge base

def kb_search(query: str, top_k: int = 3, threshold: float = 0.0) -> list[dict]:
    """Keyword overlap per policy file, scores in 0..1 as the contract requires."""
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3}
    scored = []
    for topic, text in DOCS.items():
        hits = sum(1 for w in words if w in text.lower())
        score = round(hits / max(1, len(words)), 3)
        if score > threshold:
            scored.append({"id": f"ext_{topic}", "text": text, "metadata": {"topic": topic}, "scores": {"search_score": score}})
    return sorted(scored, key=lambda m: -m["scores"]["search_score"])[:top_k]


async def search(request: Request) -> JSONResponse:
    if SECRET and request.headers.get("authorization") != f"Bearer {SECRET}":
        return JSONResponse({"error": "bad bearer token"}, status_code=401)
    body = await request.json()
    matches = kb_search(body.get("query", ""), int(body.get("top_k") or 3), float(body.get("threshold") or 0.0))
    print(f"search   {body.get('query', '')[:50]!r:52} -> {[m['id'] for m in matches]}", flush=True)
    return JSONResponse({"matches": matches})


# ------------------------------------------------------------------ module 14: webhook receiver

async def receive(request: Request) -> JSONResponse:
    prefix = request.path_params.get("prefix", "default")
    body = await request.body()
    valid: bool | None = None
    if SECRET:
        expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(expected, request.headers.get("x-orq-signature", ""))
    event = json.loads(body or b"{}")
    EVENTS.append({"prefix": prefix, "type": event.get("type"), "id": event.get("id"), "created": event.get("created"),
                   "signature_valid": valid, "data": event.get("data")})
    del EVENTS[:-500]
    print(f"{prefix:<10} {event.get('type')!s:<22} {event.get('id')} signature_valid={valid}", flush=True)
    return JSONResponse({"ok": True})


async def events(request: Request) -> JSONResponse:
    prefix = request.path_params.get("prefix")
    return JSONResponse({"events": [e for e in EVENTS if not prefix or e["prefix"] == prefix]})


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "verifying": bool(SECRET), "events": len(EVENTS), "kb_docs": sorted(DOCS)})


app = Starlette(routes=[
    Route("/search", search, methods=["POST"]),
    Route("/health", health),
    Route("/events", events),
    Route("/{prefix}/events", events),
    Route("/{prefix}", receive, methods=["POST"]),
    Route("/", receive, methods=["POST"]),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8001")))
