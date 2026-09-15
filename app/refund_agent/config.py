"""Environment-driven settings. One place, no magic."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "app" / "data"
SHELL_API_KEY = os.environ.get(
    "ORQ_API_KEY", ""
).strip()  # what the shell exported, before .env overrides it (the orq CLI login uses this one)
load_dotenv(
    os.environ.get("ORQ_ENV_FILE", ROOT / ".env"), override=True
)  # repo .env wins over a stale shell export; ORQ_ENV_FILE swaps it for a seeded-failure run


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default_factory=lambda: _env("ORQ_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("ORQ_BASE_URL", "https://my.orq.ai").rstrip("/")
    )
    project: str = field(default_factory=lambda: _env("ORQ_PROJECT", "orq-workshop"))
    prefix: str = field(default_factory=lambda: _env("WS_PREFIX", "ws"))
    model: str = field(default_factory=lambda: _env("MODEL", "openai/gpt-5.6-luna"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "openai/gpt-5.6-luna"))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "openai/text-embedding-3-large")
    )
    identity_id: str = field(default_factory=lambda: _env("IDENTITY_ID", "customer-user_001"))
    tracing: str = field(default_factory=lambda: _env("TRACING", "gateway"))
    mcp_server_url: str = field(default_factory=lambda: _env("MCP_SERVER_URL"))
    # Public base URL of app/edge.py (a tunnel to your laptop, or the instance the room shares). Module 09
    # registers `<edge_url>/search` as an external knowledge base; module 14 delivers webhooks to
    # `<edge_url>/<prefix>` unless WS_WEBHOOK_URL says otherwise.
    edge_url: str = field(default_factory=lambda: _env("WS_EDGE_URL").rstrip("/"))
    webhook_url: str = field(
        default_factory=lambda: _env("WS_WEBHOOK_URL")
        or (f"{_env('WS_EDGE_URL').rstrip('/')}/{_env('WS_PREFIX', 'ws')}" if _env("WS_EDGE_URL") else "https://httpbin.org/post")
    )
    webhook_secret: str = field(default_factory=lambda: _env("WS_WEBHOOK_SECRET"))
    shell_api_key: str = SHELL_API_KEY

    @property
    def router_url(self) -> str:
        return f"{self.base_url}/v3/router"

    @property
    def otel_url(self) -> str:
        return f"{self.base_url}/v2/otel"

    def key(self, name: str) -> str:
        """Entity key with the workshop prefix, e.g. ws-refund-agent."""
        return f"{self.prefix}-{name}"

    @property
    def path(self) -> str:
        """Entity storage path. Workspace keys need `<project>/<folder>`; project keys just `<folder>`."""
        return _env("ORQ_PATH", f"{self.project}/workshop")

    def require_key(self) -> Settings:
        if not self.api_key:
            raise SystemExit(
                "ORQ_API_KEY is empty. Copy .env.example to .env or run `orq setup --local`."
            )
        return self


settings = Settings()
