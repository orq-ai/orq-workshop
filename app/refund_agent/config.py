"""Every setting the app reads, in one place, all from the environment.

The repo `.env` is loaded on import and wins over the shell, so a stale `ORQ_API_KEY` exported
months ago cannot hijack a workshop run. The one value the shell keeps is `SHELL_API_KEY`: the
`orq` CLI logged in with that credential, and `entities.rules_api` falls back to it when the
repo key gets a 403.

Modules read `settings.<field>`; nothing else in `app/` touches `os.environ`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "app" / "data"

# What the shell exported, captured before .env overrides it: the orq CLI login uses this one.
SHELL_API_KEY = os.environ.get("ORQ_API_KEY", "").strip()

# The repo .env wins over a stale shell export. ORQ_ENV_FILE swaps in another file for a
# seeded-failure run, without touching the real .env.
load_dotenv(os.environ.get("ORQ_ENV_FILE", ROOT / ".env"), override=True)


def _env(name: str, default: str = "") -> str:
    """One variable, stripped; the default (empty by default) when it is unset."""
    return os.environ.get(name, default).strip()


def _default_webhook_url() -> str:
    """WS_WEBHOOK_URL if set; else `<edge_url>/<prefix>` when the edge is public; else httpbin."""
    explicit = _env("WS_WEBHOOK_URL")
    if explicit:
        return explicit
    edge_url = _env("WS_EDGE_URL")
    if edge_url:
        return f"{edge_url.rstrip('/')}/{_env('WS_PREFIX', 'ws')}"
    return "https://httpbin.org/post"


@dataclass(frozen=True)
class Settings:
    """Read once at import; `settings` below is the single instance the whole app shares."""

    api_key: str = field(default_factory=lambda: _env("ORQ_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("ORQ_BASE_URL", "https://my.orq.ai").rstrip("/")
    )
    project: str = field(default_factory=lambda: _env("ORQ_PROJECT", "orq-workshop"))
    # Every entity key starts with this, so `entities reset` can find what the workshop created.
    prefix: str = field(default_factory=lambda: _env("WS_PREFIX", "ws"))
    model: str = field(default_factory=lambda: _env("MODEL", "openai/gpt-5.6-luna"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "openai/gpt-5.6-luna"))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "openai/text-embedding-3-large")
    )
    identity_id: str = field(default_factory=lambda: _env("IDENTITY_ID", "customer-user_001"))
    # "gateway" (default): the gateway traces every model call by itself.
    # "otel": module 02 adds our own spans around the loop and each tool (see tracing.py).
    tracing: str = field(default_factory=lambda: _env("TRACING", "gateway"))
    mcp_server_url: str = field(default_factory=lambda: _env("MCP_SERVER_URL"))
    # Public base URL of app/edge.py (a tunnel to your laptop, or the instance the room shares).
    # Module 09 registers `<edge_url>/search` as an external knowledge base; module 14 delivers
    # webhooks to `<edge_url>/<prefix>` unless WS_WEBHOOK_URL says otherwise.
    edge_url: str = field(default_factory=lambda: _env("WS_EDGE_URL").rstrip("/"))
    webhook_url: str = field(default_factory=_default_webhook_url)
    webhook_secret: str = field(default_factory=lambda: _env("WS_WEBHOOK_SECRET"))
    shell_api_key: str = SHELL_API_KEY

    @property
    def router_url(self) -> str:
        """The OpenAI-compatible gateway: what `make_openai_client` points the OpenAI SDK at."""
        return f"{self.base_url}/v3/router"

    @property
    def otel_url(self) -> str:
        """Where tracing.py ships OTLP spans."""
        return f"{self.base_url}/v2/otel"

    def key(self, name: str) -> str:
        """Entity key with the workshop prefix, e.g. ws-refund-agent."""
        return f"{self.prefix}-{name}"

    @property
    def path(self) -> str:
        """Entity storage path. Workspace keys need `<project>/<folder>`; project keys just `<folder>`."""
        return _env("ORQ_PATH", f"{self.project}/workshop")

    def require_key(self) -> Settings:
        """Fail early with a fix, instead of a 401 three calls later."""
        if not self.api_key:
            raise SystemExit(
                "ORQ_API_KEY is empty. Copy .env.example to .env or run `orq setup --local`."
            )
        return self


settings = Settings()
