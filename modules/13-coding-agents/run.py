"""Module 13 starter: what `orq connect` and `orq launch` would change, which skills ship in the CLI,
and what a coding-agent session costs once it runs through the gateway.

A coding agent is one more traced, budgeted client of your workspace. Nothing here writes to
~/.orq, ~/.claude or an agent config: every connect/launch call is --dry-run, and keys are redacted.

Fill in the TODOs. The script runs as is; a step with an unfilled TODO says so in its output block.
Run it with `uv run python modules/13-coding-agents/run.py`. The solution is in solution/run.py.
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
AGENTS = ["claude"]  # TODO: add opencode, pi and codex and compare which files each one would touch


def cli(*args: str, check: bool = True, trim: bool = True) -> str:
    """Run `orq <args>` with the repo key; return stdout and stderr with every key redacted."""
    completed = subprocess.run(["orq", *args], env=ENV, capture_output=True, text=True, check=check)
    out = SECRET.sub(r"\1<redacted>", completed.stdout + completed.stderr)
    # OPENCODE_CONFIG_CONTENT carries the whole model catalogue on one line; keep the README readable.
    if not trim:
        return out
    return "\n".join(line if len(line) < 400 else line[:300] + f" ... ({len(line) - 300} more chars)" for line in out.splitlines())


# ── Step 1 · What is wired, and what --local would change ──
# `orq connect --status` lists what each agent has; a --local dry run per agent lists the files a
# project-local wiring would write.
def step_1_connect_status() -> None:
    """Print the connect status and one --local dry run per agent in AGENTS."""
    print("── Step 1 · What is wired, and what --local would change ───")
    if AGENTS == ["claude"]:
        print("TODO     : fill in AGENTS with opencode, pi and codex, then rerun")
    print("command  : orq connect --status")
    print(cli("connect", "--status"))
    for agent in AGENTS:
        print(f"command  : orq connect {agent} --local --dry-run")
        print(cli("connect", agent, "--local", "--dry-run"))


# ── Step 2 · What orq launch injects ──
# `orq launch <agent>` wires one session through environment variables and leaves nothing on disk.
def step_2_launch_dry_run() -> None:
    """Print the env `orq launch` would give each agent."""
    print("── Step 2 · What orq launch injects ───────────────────")
    launched = ["claude"]  # TODO: add opencode; note the env vars each agent gets
    if launched == ["claude"]:
        print("TODO     : fill in opencode next to claude, then rerun")
    for agent in launched:
        print(f"command  : orq launch {agent} --dry-run")
        print(cli("launch", agent, "--dry-run", check=False))


# ── Step 3 · The skills that ship in the CLI ──
# `orq launch` links these for a session, `orq connect skills` installs them permanently.
def step_3_bundled_skills() -> None:
    """List the skills materialized from the CLI binary."""
    print("── Step 3 · The skills that ship in the CLI ───────────")
    manifest = Path.home() / ".orq" / "materialized-skills.json"
    if not manifest.exists():
        print("skills   : no ~/.orq/materialized-skills.json yet: run `orq launch <agent>` once, or `orq connect --status`")
        return
    generation = Path(json.loads(manifest.read_text())["generation"])
    print("TODO     : fill in the `description:` of each SKILL.md next to its name, then rerun")
    print(f"snapshot : {generation}")
    for skill_md in sorted(generation.glob("*/SKILL.md")):
        print(f"    {skill_md.parent.name}")  # TODO: print the `description:` line of each SKILL.md front matter


# ── Step 4 · Coding-agent sessions as traces ──
# A coding-agent session is one session_id shared by every model call it made.
def step_4_sessions_as_traces() -> None:
    """Group the last 24h of coding-agent traces by session id and print what each session cost."""
    raw = cli("traces", "search", "--from", "24h", "--to", "now", "--limit", "200", "-o", "json", trim=False)
    traces = json.loads(raw)["data"]
    sessions: dict[str, list[dict]] = defaultdict(list)
    for trace in traces:
        if trace["name"].startswith("messages.anthropic"):  # TODO: also match attributes.orq.coding_assistant (Codex, others)
            sessions[trace["session_id"]].append(trace)

    print("── Step 4 · Coding-agent sessions as traces ───────────")
    print("TODO     : fill in the coding_assistant match and the token counts, then rerun")
    print(f"sessions : {len(sessions)} in the last 24h")
    for session_id, calls in sessions.items():
        cost = sum(call["cost"]["total"] for call in calls)
        print(f"session  : {session_id}  calls={len(calls)} cost=${cost:.4f}")  # TODO: add tokens and cached tokens


if __name__ == "__main__":
    step_1_connect_status()
    step_2_launch_dry_run()
    step_3_bundled_skills()
    step_4_sessions_as_traces()
    print(f"next     : open {settings.base_url}/traces and filter by model anthropic/claude-sonnet-5")
