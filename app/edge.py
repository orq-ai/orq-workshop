"""The edge: the one small HTTP service orq calls back into during the workshop.

Two contracts in one process, so one tunnel (or one hosted instance) serves both:

    POST /search             module 09, external knowledge base (registered as api_url): {query, top_k, threshold, ...}
                             -> {"matches": [{id, text, metadata, scores}]}, keyword scoring over app/data/kb
    POST /<prefix>           module 14, webhook delivery for one participant (WS_PREFIX), HMAC verified
    GET  /<prefix>/events    what arrived for that prefix, newest last
    GET  /events             everything, all prefixes
    GET  /health
    GET  /docs, /openapi.json  the /search contract as Swagger UI; set EDGE_DOCS=0 to hide it

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
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.schemas import SchemaGenerator

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
EDGE_DOCS = os.environ.get("EDGE_DOCS", "1") != "0"  # EDGE_DOCS=0 hides /docs; it has no auth in front of it


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
    """POST /search: check the Bearer secret orq sends as the KB's api_key, then score the query.

    The block after `---` is what SchemaGenerator reads; the handlers without one stay out of the
    schema on purpose, so the docs page describes the KB contract and not the webhook endpoints.
    ---
    summary: The external knowledge base contract (module 09).
    description: >
      Scoring is keyword overlap against the policy files, so a placeholder query such as
      "string" scores 0 and comes back with no matches: the filter is score > threshold.
    security: [{bearerAuth: []}]
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              query: {type: string, example: damaged in transit after 45 days}
              top_k: {type: integer, default: 3}
              threshold: {type: number, default: 0.0}
            example:
              query: damaged in transit after 45 days
              top_k: 3
              threshold: 0.0
    responses:
      200:
        description: matches, highest search_score first
      401:
        description: the Authorization bearer did not match WS_WEBHOOK_SECRET
    """
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
    ---
    summary: Webhook delivery (module 14). A bad signature is recorded, not rejected.
    requestBody:
      content:
        application/json:
          schema: {type: object, description: the orq event envelope}
    responses:
      200:
        description: stored; signature_valid is true, false, or null when no secret is set
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
    """GET /events or /<prefix>/events: what arrived, newest last, optionally for one participant.
    ---
    summary: The webhook deliveries this process is holding, newest last.
    responses:
      200:
        description: events, narrowed to one participant when the path carries a prefix
    """
    prefix = request.path_params.get("prefix")
    return JSONResponse({"events": [event for event in EVENTS if not prefix or event["prefix"] == prefix]})


async def health(request: Request) -> JSONResponse:
    """GET /health: is the secret set, how many events are held, which policy files were loaded.
    ---
    summary: Liveness, plus what this process has loaded.
    responses:
      200:
        description: ok, whether a secret is configured, the event count, the policy files
    """
    return JSONResponse({"ok": True, "verifying": bool(SECRET), "events": len(EVENTS), "kb_docs": sorted(DOCS)})


# ------------------------------------------------------------------ optional: the /search contract as Swagger UI

schemas = SchemaGenerator(
    {
        "openapi": "3.0.0",
        "info": {"title": "orq workshop edge", "version": "1.0"},
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }
)
DOCUMENTED = (search, receive, events, health)  # every handler whose docstring carries a `---` block

# ponytail: Swagger UI from a CDN, so the page needs internet in the browser; vendor the two
# assets if the room is offline.
SWAGGER_UI = """<!doctype html><html><head><title>orq workshop edge</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"></head>
<body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url: "openapi.json", dom_id: "#ui"})</script>
</body></html>"""


async def openapi(request: Request) -> JSONResponse:
    """GET /openapi.json: the schema built from the handler docstrings."""
    # Only the handlers listed in DOCUMENTED. SchemaGenerator yaml-parses whatever follows the last
    # `---` in a docstring, so a handler with a plain prose docstring is not skipped: its prose is
    # parsed as YAML and a colon in a sentence raises, which would make this endpoint a 500.
    documented = [route for route in request.app.routes if getattr(route, "endpoint", None) in DOCUMENTED]
    return JSONResponse(schemas.get_schema(routes=documented))


async def docs(request: Request) -> HTMLResponse:
    """GET /docs: Swagger UI pointed at /openapi.json."""
    return HTMLResponse(SWAGGER_UI)


# Route order matters: the literal paths come before the catch-all /{prefix}, which matches any
# single segment and would answer 405 for a GET of /docs.
app = Starlette(
    routes=[
        Route("/search", search, methods=["POST"]),
        Route("/health", health),
        Route("/events", events),
        *([Route("/docs", docs), Route("/openapi.json", openapi)] if EDGE_DOCS else []),
        Route("/{prefix}/events", events),
        Route("/{prefix}", receive, methods=["POST"]),
        Route("/", receive, methods=["POST"]),
    ]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8001")))
