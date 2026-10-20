"""Every setting the app reads, in one place, all from the environment.

The repo `.env` is loaded on import and wins over the shell, so a stale `ORQ_API_KEY` exported
months ago cannot hijack a workshop run. The one value the shell keeps is `SHELL_API_KEY`: the
`orq` CLI logged in with that credential, and `entities.rules_api` falls back to it when the
repo key gets a 403.

Modules read `settings.<field>`; nothing else in `app/` touches `os.environ`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

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


_renew_lock = threading.Lock()  # one `orq` renewal at a time; concurrent requests wait, then read the fresh file


def _oauth_session(base_url: str, margin: int = 300) -> tuple[str, str]:
    """(workspace token, workspace key) from the `orq auth login` session for this host, or ("", "").

    The token is the one the CLI keeps per workspace; it lasts about an hour and the CLI renews it.
    "Fresh" means more than `margin` seconds left, so a turn does not run out halfway.
    """
    try:
        session = json.loads((Path.home() / ".orq" / "sessions" / f"{urlparse(base_url).hostname}.json").read_text())
        workspace = session["activeWorkspaceKey"]
        entry = session["workspaceTokens"][workspace]
        expires = datetime.fromisoformat(entry["expiresAt"].replace("Z", "+00:00"))
        fresh = expires - datetime.now(timezone.utc) > timedelta(seconds=margin)
        return (entry["token"] if fresh else ""), workspace
    except (OSError, ValueError, KeyError, TypeError):
        return "", ""


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
    # Workspace key (the slug in Studio URLs, `active_workspace_key` in `orq doctor`). The API key
    # only carries the workspace UUID, so `make chat` reads this to deep-link a trace.
    workspace: str = field(default_factory=lambda: _env("ORQ_WORKSPACE"))
    # Every entity key starts with this, so `entities reset` can find what the workshop created.
    # Lowercased: MCP server and smart router keys reject uppercase.
    prefix: str = field(default_factory=lambda: _env("WS_PREFIX", "ws").lower())
    model: str = field(default_factory=lambda: _env("MODEL", "openai/gpt-6-luna"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "openai/gpt-6-luna"))
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

    def bearer(self) -> str:
        """The credential to send: ORQ_API_KEY, else the OAuth token of the `orq auth login` session.

        The session token is renewed by a cheap CLI call when it is missing or about to expire, so
        call this per request instead of keeping the value. Never log it.
        """
        if self.api_key:
            return self.api_key
        token, _ = _oauth_session(self.base_url)
        if not token:
            with _renew_lock:
                token, _ = _oauth_session(self.base_url)  # another thread may have renewed it meanwhile
                if not token:
                    env = {k: v for k, v in os.environ.items() if k not in ("ORQ_API_KEY", "ORQ_PROJECT", "ORQ_WORKSPACE")}
                    try:
                        subprocess.run(
                            ["orq", "projects", "list", "--limit", "1", "--no-input", "-o", "json"],
                            env=env, capture_output=True, timeout=30, check=False, stdin=subprocess.DEVNULL,  # a CLI waiting on stdin would hang
                        )
                    except (OSError, subprocess.SubprocessError):
                        pass  # no CLI: the error below says what to do
                    token, _ = _oauth_session(self.base_url, margin=0)  # the CLI may keep a token that is still valid
        if not token:
            raise SystemExit(
                "ORQ_API_KEY is empty and there is no usable `orq` login. "
                "Copy .env.example to .env or run `orq auth login`."
            )
        return token

    def studio_workspace(self) -> str:
        """Workspace key for Studio links: the OAuth session's active one when there is no API key
        (that is where the calls go), else ORQ_WORKSPACE."""
        return (_oauth_session(self.base_url)[1] if not self.api_key else "") or self.workspace

    def require_key(self) -> Settings:
        """Fail early with a fix, instead of a 401 three calls later."""
        self.bearer()
        return self


settings = Settings()
