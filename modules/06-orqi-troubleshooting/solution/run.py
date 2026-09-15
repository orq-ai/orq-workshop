# %% [markdown]
# # 06 · Troubleshooting with orqi
#
# orqi is the orq helper agent: it operates the platform, it does not build your app. Modules 01
# to 05 left timeouts, bad model ids and guardrail blocks in the workspace; this module finds them
# and hands them to orqi. Three steps: find a failed trace with the `orq` CLI, reproduce a
# client-side failure without touching `.env`, and ask orqi about both as one-shot prompts.
#
# orqi and the `orq` CLI read `ORQ_API_KEY` from the environment; the cells below pass the repo key
# explicitly, so the answers are about the same workspace the app writes to.
#
# This file is both the solution script (`make m06`) and the notebook source (`make notebooks`).
# Run the cells top to bottom. Step 3 takes a few minutes: each orqi answer takes 15 s to 2 min.

# %%
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter

from openai import OpenAI

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Hi, I want a refund for order ord_a1, I changed my mind."
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PROGRESS = re.compile(r"^(GOAL:|\[\s*[x~ ]\s*\])")  # orqi prints its plan as it goes; keep only the answer
ENV = {**os.environ, "ORQ_API_KEY": settings.require_key().api_key, "CI": "1"}  # CI=1: no update check
TRACES_URL = f"{settings.base_url}/traces"


def cli(*args: str) -> str:
    """Run `orq <args>` with the repo key and return stdout. Raises when the command fails."""
    return subprocess.run(["orq", *args], env=ENV, capture_output=True, text=True, check=True).stdout


def orqi(prompt: str) -> str:
    """One-shot orqi. Returns the header line and the final answer, without the progress lines."""
    if not shutil.which("orqi"):
        return "orqi not on PATH. Install: curl -fsSL https://raw.githubusercontent.com/orq-ai/orqi/main/install.sh | sh"
    completed = subprocess.run(["orqi", prompt], env=ENV, capture_output=True, text=True)
    lines = [ANSI.sub("", line) for line in (completed.stderr + completed.stdout).splitlines() if line.strip()]  # header is on stderr
    kept = [line for line in lines if not PROGRESS.match(line)]
    return "\n".join(kept)

# %% [markdown]
# ## Step 1 · Find a failed trace with the CLI
#
# `orq traces search` returns the last traces as JSON; a failed one has `status == "error"` and the
# HTTP status the gateway answered in `attributes.http.response.status_code`. Counting by status
# tells you what kind of failures you are looking at before you read a single trace.

# %%
# `orq traces search` needs both bounds; relative values like 3h / now are fine.
traces = json.loads(cli("traces", "search", "--from", "3h", "--to", "now", "--limit", "200", "-o", "json"))["data"]
errors = [trace for trace in traces if trace["status"] == "error"]
by_status = Counter(str(trace["attributes"].get("http", {}).get("response", {}).get("status_code")) for trace in errors)
trace_id = errors[0]["trace_id"] if errors else None

print("── Step 1 · Find a failed trace with the CLI ──────────")
print(f"window   : last 3h, {len(traces)} traces")
print(f"errors   : {len(errors)}")
print(f"statuses : {', '.join(f'HTTP {status} × {count}' for status, count in by_status.items()) or '-'}")
for trace in errors[:3]:
    print(f"failed   : {trace['trace_id']}  {trace['name']:<16} {trace['attributes'].get('error', {}).get('type', '-')}")
print("next     : step 3 asks orqi why the first of these failed")

# %% [markdown]
# ## Step 2 · Break the client, not the gateway
#
# A wrong `ORQ_BASE_URL` never reaches the gateway, so there is no trace for orqi to read: the error
# text is all you have. `.env` overrides the shell by design, so a wrong base URL is reproduced here
# in code: the same OpenAI client the app uses, pointed at a wrong URL, no retries. The app itself
# is untouched.

# %%
broken = OpenAI(api_key=settings.api_key, base_url=f"{settings.base_url}/broken", max_retries=0)

print("── Step 2 · Break the client, not the gateway ─────────")
try:
    chat(QUESTION, client=broken)
except Exception as exc:  # noqa: BLE001
    response = getattr(exc, "response", None)
    where = f" on {response.request.method} {response.request.url}, x-orq-trace-id={response.headers.get('x-orq-trace-id')}" if response is not None else ""
    error_text = f"{type(exc).__module__}.{type(exc).__name__}: {exc}{where}"  # pasted verbatim into the orqi prompt in step 3
    print(f"error    : {type(exc).__module__}.{type(exc).__name__}: {exc}")
    if response is not None:
        print(f"request  : {response.request.method} {response.request.url}")
        print(f"trace    : {response.headers.get('x-orq-trace-id')} (no trace id: the request never reached the gateway)")
    print("next     : step 3 pastes this error into orqi")
else:
    raise SystemExit("the broken base URL did not fail; check ORQ_BASE_URL")

# %% [markdown]
# ## Step 3 · Ask orqi
#
# Four one-shot prompts: workspace health, errors grouped by root cause, the trace from step 1, and
# the client error from step 2. orqi picks the skill for each (`workspace-health-check`,
# `investigate-root-cause`, ...) and prints its plan as it goes; `orqi()` keeps only the answer.
# orqi can also run shell commands in the current directory: in step 3d it may run `make smoke`.

# %%
prompts = [
    "check workspace health",
    "list the traces with errors from the last 2 hours and group them by root cause",
]
if trace_id:
    prompts.append(f"why did trace {trace_id} fail?")
prompts.append(
    "make smoke in my repo fails with this error, diagnose it and tell me what to fix: "
    f"{error_text}. The app uses the OpenAI SDK with base_url built from ORQ_BASE_URL in .env."
)

# %%
for i, prompt in enumerate(prompts, start=1):
    header = f"── Step 3{chr(96 + i)} · Ask orqi "
    print(header + "─" * (55 - len(header)))
    print(f"prompt   : {prompt[:70]}{'…' if len(prompt) > 70 else ''}")
    print("answer   :")
    print(orqi(prompt))
print(f"next     : open {TRACES_URL} and search one of the ids above")

# %% [markdown]
# ## What to take away
#
# - The CLI finds failures (`orq traces search`), orqi explains them: it walks the span tree with
#   the same MCP tools your coding agent gets.
# - A failure that never reached the gateway has no trace. Give orqi the exact error text instead.
# - orqi operates the platform and needs no repo; `orq launch <agent>` builds your app.
