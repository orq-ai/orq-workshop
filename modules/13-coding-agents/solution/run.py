"""Module 13 solution: what `orq connect` and `orq launch` would change, which skills ship in the CLI,
and what a coding-agent session costs once it runs through the gateway.

Nothing here writes to ~/.orq, ~/.claude or an agent config: every connect/launch call is --dry-run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from app.refund_agent.config import settings

ENV = {**os.environ, "ORQ_API_KEY": settings.require_key().api_key}
SECRET = re.compile(r"((?:AUTH_TOKEN|API_KEY|apiKey|token)[=\":]+)[A-Za-z0-9._{}:$-]{6,}")
AGENTS = ["claude", "opencode", "pi", "codex"]


def cli(*args: str, check: bool = True, trim: bool = True) -> str:
    p = subprocess.run(["orq", *args], env=ENV, capture_output=True, text=True, check=check)
    out = SECRET.sub(r"\1<redacted>", p.stdout + p.stderr)
    # OPENCODE_CONFIG_CONTENT carries the whole model catalogue on one line; keep the README readable.
    if not trim:
        return out
    return "\n".join(l if len(l) < 400 else l[:300] + f" ... ({len(l) - 300} more chars)" for l in out.splitlines())


def step_1_connect_status() -> None:
    print("[1] orq connect --status")
    print(cli("connect", "--status"))
    for agent in AGENTS:
        print(f"[1] orq connect {agent} --local --dry-run")
        print(cli("connect", agent, "--local", "--dry-run"))


def step_2_launch_dry_run() -> None:
    for agent in ["claude", "opencode"]:
        print(f"[2] orq launch {agent} --dry-run")
        print(cli("launch", agent, "--dry-run", check=False))


def step_3_bundled_skills() -> None:
    # `orq launch` links these for a session, `orq connect skills` installs them permanently.
    manifest = Path.home() / ".orq" / "materialized-skills.json"
    if not manifest.exists():
        print("[3] no ~/.orq/materialized-skills.json yet: run `orq launch <agent>` once, or `orq connect --status`")
        return
    gen = Path(json.loads(manifest.read_text())["generation"])
    print(f"[3] skills bundled in the CLI, materialized under {gen}")
    for skill_md in sorted(gen.glob("*/SKILL.md")):
        front = skill_md.read_text().split("---")[1]
        desc = " ".join(l.strip() for l in front.split("description:")[1].split("allowed-tools:")[0].split("\n")).strip(" >-")
        print(f"    {skill_md.parent.name:<32} {desc[:90]}")


def step_4_sessions_as_traces() -> None:
    # A coding-agent session is one session_id shared by every model call it made.
    raw = cli("traces", "search", "--from", "24h", "--to", "now", "--limit", "200", "--json", trim=False)
    data = json.loads(raw)["data"]
    sessions: dict[str, list[dict]] = defaultdict(list)
    for t in data:
        if t["attributes"].get("orq", {}).get("coding_assistant") or t["name"].startswith("messages.anthropic"):
            sessions[t["session_id"]].append(t)
    print(f"[4] coding-agent sessions in the last 24h: {len(sessions)}")
    for sid, calls in sorted(sessions.items(), key=lambda kv: -sum(c["cost"]["total"] for c in kv[1])):
        cost = sum(c["cost"]["total"] for c in calls)
        tokens = sum(c["usage"]["prompt_tokens"] + c["usage"]["completion_tokens"] for c in calls)
        cached = sum(c["usage"].get("prompt_cached_tokens", 0) for c in calls)
        model = calls[0]["attributes"].get("gen_ai", {}).get("response", {}).get("model", "-")
        print(f"    session {sid}  calls={len(calls)} model={model} tokens={tokens} cached={cached} cost=${cost:.4f}")
        print(f"    orq traces query-oql --from 24h --to now --oql 'fetch traces | filter session_id == \"{sid}\"'")


if __name__ == "__main__":
    step_1_connect_status()
    step_2_launch_dry_run()
    step_3_bundled_skills()
    step_4_sessions_as_traces()
    print(f"\nopen {settings.base_url}/traces and filter by model anthropic/claude-sonnet-5")
