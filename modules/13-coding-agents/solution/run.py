# %% [markdown]
# # 13 · Coding agents
#
# What `orq connect` and `orq launch` would change, which skills ship in the CLI, and what a
# coding-agent session costs once it runs through the gateway. A coding agent is one more traced,
# budgeted client of your workspace: its model calls are traces grouped by session id.
#
# | | |
# |---|---|
# | **Time** | 25 min |
# | **Prerequisites** | module 00; at least one of Claude Code, OpenCode, Pi or Codex installed |
# | **You will have** | a dry-run of every file `orq connect` would touch, the exact env `orq launch` injects, the list of skills that ship in the CLI, one coding-agent session visible as traces with its cost, and a checklist to repeat this in your own repo |
#
# Nothing here writes to `~/.orq`, `~/.claude` or an agent config: every connect and launch call
# is `--dry-run`, and every key in the output is redacted.
#
# This file is both the solution script (`make m13`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
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
    """Run `orq <args>` with the repo key; return stdout and stderr with every key redacted."""
    completed = subprocess.run(["orq", *args], env=ENV, capture_output=True, text=True, check=check)
    out = SECRET.sub(r"\1<redacted>", completed.stdout + completed.stderr)
    # OPENCODE_CONFIG_CONTENT carries the whole model catalogue on one line; keep the README readable.
    if not trim:
        return out
    return "\n".join(line if len(line) < 400 else line[:300] + f" ... ({len(line) - 300} more chars)" for line in out.splitlines())

# %% [markdown]
# ## Step 1 · What is wired, and what `--local` would change
#
# `orq connect --status` lists what each agent already has (`gateway`, `skills`, `mcp`). Then a dry
# run per agent shows which files a project-local wiring would write: `--local` scopes `mcp` and
# `skills` to this repo, `gateway` is machine-wide either way.

# %%
print("── Step 1 · What is wired, and what --local would change ───")
print("command  : orq connect --status")
print(cli("connect", "--status"))
for agent in AGENTS:
    print(f"command  : orq connect {agent} --local --dry-run")
    print(cli("connect", agent, "--local", "--dry-run"))
print("next     : read the file column; that is what `orq connect --local` would write in this repo")

# %% [markdown]
# ## Step 2 · What `orq launch` injects
#
# `orq launch <agent>` wires one session through environment variables and leaves nothing on disk.
# The dry run prints the binary, its args and the env, with the key redacted. `check=False`: a
# missing agent binary should not stop the rest of the module.

# %%
print("── Step 2 · What orq launch injects ───────────────────")
for agent in ["claude", "opencode"]:
    print(f"command  : orq launch {agent} --dry-run")
    print(cli("launch", agent, "--dry-run", check=False))
print("next     : ANTHROPIC_BASE_URL points at the gateway, and ANTHROPIC_API_KEY is empty on purpose")

# %% [markdown]
# ## Step 3 · The skills that ship in the CLI
#
# The skills live inside the `orq` binary and are materialized under `~/.orq/snapshot/gen-<id>/`;
# `~/.orq/materialized-skills.json` records where. `orq launch` links these for a session,
# `orq connect skills` installs them permanently.

# %%
manifest = Path.home() / ".orq" / "materialized-skills.json"

print("── Step 3 · The skills that ship in the CLI ───────────")
if not manifest.exists():
    print("skills   : no ~/.orq/materialized-skills.json yet: run `orq launch <agent>` once, or `orq connect --status`")
else:
    generation = Path(json.loads(manifest.read_text())["generation"])
    print(f"snapshot : {generation}")
    for skill_md in sorted(generation.glob("*/SKILL.md")):
        front_matter = skill_md.read_text().split("---")[1]
        # the description is a folded YAML block that ends where allowed-tools starts
        description = " ".join(line.strip() for line in front_matter.split("description:")[1].split("allowed-tools:")[0].split("\n")).strip(" >-")
        print(f"    {skill_md.parent.name:<32} {description[:90]}")
    print("next     : paste a skill name into your coding agent's prompt, e.g. 'use the orq-setup-observability skill'")

# %% [markdown]
# ## Step 4 · Coding-agent sessions as traces
#
# A coding-agent session is one `session_id` shared by every model call it made. Claude Code calls
# are named `messages.anthropic`; other agents (Codex) are tagged `orq.coding_assistant`. Sessions
# are sorted by cost, highest first.

# %%
raw = cli("traces", "search", "--from", "24h", "--to", "now", "--limit", "200", "-o", "json", trim=False)
traces = json.loads(raw)["data"]
sessions: dict[str, list[dict]] = defaultdict(list)
for trace in traces:
    if trace["attributes"].get("orq", {}).get("coding_assistant") or trace["name"].startswith("messages.anthropic"):
        sessions[trace["session_id"]].append(trace)

print("── Step 4 · Coding-agent sessions as traces ───────────")
print(f"sessions : {len(sessions)} in the last 24h")
for session_id, calls in sorted(sessions.items(), key=lambda item: -sum(call["cost"]["total"] for call in item[1])):
    cost = sum(call["cost"]["total"] for call in calls)
    tokens = sum(call["usage"]["prompt_tokens"] + call["usage"]["completion_tokens"] for call in calls)
    cached = sum(call["usage"].get("prompt_cached_tokens", 0) for call in calls)
    model = calls[0]["attributes"].get("gen_ai", {}).get("response", {}).get("model", "-")
    print(f"session  : {session_id}  calls={len(calls)} model={model} tokens={tokens} cached={cached} cost=${cost:.4f}")
    print(f"query    : orq traces query-oql --from 24h --to now --oql 'fetch traces | filter session_id == \"{session_id}\"'")
print(f"next     : open {settings.base_url}/traces and filter by model anthropic/claude-sonnet-5")

# %% [markdown]
# ## What to take away
#
# - `orq launch` wires one session through env vars; `orq connect` writes config files, and
#   `--local` keeps `mcp` and `skills` inside the repo.
# - The skills ship inside the CLI binary; linking them costs nothing and needs no credential.
# - Every model call a coding agent makes is a trace with tokens and cost, grouped by session id,
#   so budgets and identities apply to developers too.
