"""`settings.bearer()`: ORQ_API_KEY wins; otherwise the `orq auth login` session token, renewed by the CLI. No network."""

import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.refund_agent.config import settings

HOST = "my.orq.ai"
KEYLESS = replace(settings, api_key="", base_url=f"https://{HOST}", workspace="")


def write_session(home, token, expires_in):
    expires = (datetime.now(UTC) + timedelta(seconds=expires_in)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    path = home / ".orq" / "sessions" / f"{HOST}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"activeWorkspaceKey": "acme", "workspaceTokens": {"acme": {"token": token, "expiresAt": expires}}}))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_api_key_wins(home):
    write_session(home, "session-token", 3600)
    assert replace(KEYLESS, api_key="key").bearer() == "key"


def test_fresh_session_token_is_used(home):
    write_session(home, "session-token", 3600)
    assert KEYLESS.bearer() == "session-token"
    assert KEYLESS.studio_workspace() == "acme"


def test_expired_token_is_renewed_by_the_cli(home, monkeypatch):
    write_session(home, "old", -10)
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd[0], "ORQ_API_KEY" in kw["env"]))
        write_session(home, "renewed", 3600)  # what the CLI does to the session file
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KEYLESS.bearer() == "renewed"
    assert calls == [("orq", False)]


def test_unusable_session_exits_with_a_fix(home, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1))
    with pytest.raises(SystemExit, match="orq auth login"):
        KEYLESS.bearer()


def test_trace_links_follow_the_oauth_workspace_when_there_is_no_key(monkeypatch):
    from app.refund_agent import config

    monkeypatch.setattr(config, "_oauth_session", lambda base_url: ("tok", "logged-in"))
    cfg = replace(settings, api_key="", workspace="stale-env")
    assert cfg.studio_workspace() == "logged-in"
    assert replace(cfg, api_key="k").studio_workspace() == "stale-env"
