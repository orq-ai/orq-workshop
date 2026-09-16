"""Module 06 starter: orqi as the troubleshooting entry point.

orqi is the orq helper agent: it operates the platform, it does not build your app. Find a failed
trace with the CLI, reproduce a client-side failure without touching `.env`, and hand both to orqi
as one-shot prompts.

Fill in the TODOs. The script runs as is; a step with an unfilled TODO says so in its output block.
Run it with `uv run python modules/06-orqi-troubleshooting/run.py`. The solution is in solution/run.py.
"""

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


# ── Step 1 · Find a failed trace with the CLI ──
# `orq traces search` returns the last traces as JSON. Counting the failed ones by HTTP status tells
# you what kind of failures you have before you read a single trace.
def step_1_find_failed_trace() -> str | None:
    """Search the last 3 hours, count errors by HTTP status, return the first failed trace id."""
    # `orq traces search` needs both bounds; relative values like 3h / now are fine.
    traces = json.loads(cli("traces", "search", "--from", "3h", "--to", "now", "--limit", "200", "-o", "json"))["data"]
    errors = [trace for trace in traces if trace["status"] == "error"]
    by_status = Counter(str(trace["attributes"].get("http", {}).get("response", {}).get("status_code")) for trace in errors)

    print("── Step 1 · Find a failed trace with the CLI ──────────")
    print(f"window   : last 3h, {len(traces)} traces")
    print(f"errors   : {len(errors)}")
    print(f"statuses : {', '.join(f'HTTP {status} × {count}' for status, count in by_status.items()) or '-'}")
    for trace in errors[:3]:
        print(f"failed   : {trace['trace_id']}  {trace['name']:<16} {trace['attributes'].get('error', {}).get('type', '-')}")
    return errors[0]["trace_id"] if errors else None


# ── Step 2 · Break the client, not the gateway ──
# A wrong ORQ_BASE_URL never reaches the gateway, so there is no trace to read. `.env` overrides
# the shell by design, so the wrong base URL is reproduced here in code.
def step_2_break_the_client() -> str:
    """Call the agent with a client pointed at a wrong URL and return the error text for orqi."""
    # TODO: point this client at f"{settings.base_url}/broken" and set max_retries=0
    broken = OpenAI(api_key=settings.api_key, base_url=settings.router_url)

    print("── Step 2 · Break the client, not the gateway ─────────")
    try:
        chat(QUESTION, client=broken)
    except Exception as exc:  # noqa: BLE001
        response = getattr(exc, "response", None)
        where = f" on {response.request.method} {response.request.url}, x-orq-trace-id={response.headers.get('x-orq-trace-id')}" if response is not None else ""
        text = f"{type(exc).__module__}.{type(exc).__name__}: {exc}{where}"
        print(f"error    : {text}")
        return text
    print("TODO     : fill in the broken client (wrong base_url, max_retries=0), then rerun")
    return ""


# ── Step 3 · Ask orqi ──
# One-shot prompts: workspace health, errors grouped by root cause, the trace from step 1, and the
# client error from step 2. Each answer takes 15 s to 2 min.
def step_3_ask_orqi(trace_id: str | None, error_text: str) -> None:
    """Send each prompt to orqi and print its answer."""
    prompts = [
        "check workspace health",
        # TODO: add "list the traces with errors from the last 2 hours and group them by root cause"
        # TODO: add f"why did trace {trace_id} fail?" when trace_id is set
        # TODO: add a prompt that pastes error_text and asks for a diagnosis (mention ORQ_BASE_URL)
    ]
    for i, prompt in enumerate(prompts, start=1):
        header = f"── Step 3{chr(96 + i)} · Ask orqi "
        print(header + "─" * (55 - len(header)))
        if len(prompts) == 1:
            print("TODO     : fill in the other three prompts, then rerun")
        print(f"prompt   : {prompt[:70]}{'…' if len(prompt) > 70 else ''}")
        print("answer   :")
        print(orqi(prompt))


if __name__ == "__main__":
    trace_id = step_1_find_failed_trace()
    error_text = step_2_break_the_client()
    step_3_ask_orqi(trace_id, error_text)
    print(f"next     : open {settings.base_url}/traces and search one of the ids above")
