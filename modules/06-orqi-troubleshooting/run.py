"""Module 06 starter: orqi as the troubleshooting entry point.

Find a failed trace with the CLI, reproduce a client-side failure without touching `.env`,
and hand both to orqi as one-shot prompts. Fill the TODOs; the solution is in solution/run.py.
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
    return subprocess.run(["orq", *args], env=ENV, capture_output=True, text=True, check=True).stdout


def orqi(prompt: str) -> str:
    """One-shot orqi. Prints the header line and the final answer, skips the progress lines."""
    if not shutil.which("orqi"):
        return "orqi not on PATH. Install: curl -fsSL https://raw.githubusercontent.com/orq-ai/orqi/main/install.sh | sh"
    out = subprocess.run(["orqi", prompt], env=ENV, capture_output=True, text=True)
    lines = [ANSI.sub("", l) for l in (out.stderr + out.stdout).splitlines() if l.strip()]  # header is on stderr
    keep = [l for l in lines if not PROGRESS.match(l)]
    return "\n".join(keep)


def step_1_find_failed_trace() -> str | None:
    # `orq traces search` needs both bounds; relative values like 3h / now are fine.
    data = json.loads(cli("traces", "search", "--from", "3h", "--to", "now", "--limit", "200", "--json"))["data"]
    errors = [t for t in data if t["status"] == "error"]
    by_code = Counter(str(t["attributes"].get("http", {}).get("response", {}).get("status_code")) for t in errors)
    print(f"[1] traces 3h      total={len(data)} errors={len(errors)} by http status={dict(by_code)}")
    for t in errors[:3]:
        print(f"    {t['trace_id']}  {t['name']:<14} {t['attributes'].get('error', {}).get('type', '-')}")
    return errors[0]["trace_id"] if errors else None


def step_2_break_the_client() -> str:
    # `.env` overrides the shell by design, so a wrong ORQ_BASE_URL is reproduced here in code.
    # TODO: point this client at f"{settings.base_url}/broken" and set max_retries=0
    broken = OpenAI(api_key=settings.api_key, base_url=settings.router_url)
    try:
        chat(QUESTION, client=broken)
    except Exception as exc:  # noqa: BLE001
        r = getattr(exc, "response", None)
        where = f" on {r.request.method} {r.request.url}, x-orq-trace-id={r.headers.get('x-orq-trace-id')}" if r is not None else ""
        text = f"{type(exc).__module__}.{type(exc).__name__}: {exc}{where}"
        print(f"[2] broken client  {text}")
        return text
    print("[2] broken client  the call succeeded: the TODO above is not done yet")
    return ""


def step_3_ask_orqi(trace_id: str | None, error_text: str) -> None:
    prompts = [
        "check workspace health",
        # TODO: add "list the traces with errors from the last 2 hours and group them by root cause"
        # TODO: add f"why did trace {trace_id} fail?" when trace_id is set
        # TODO: add a prompt that pastes error_text and asks for a diagnosis (mention ORQ_BASE_URL)
    ]
    for i, p in enumerate(prompts, start=1):
        print(f"\n[3.{i}] orqi \"{p[:70]}{'...' if len(p) > 70 else ''}\"")
        print(orqi(p))


if __name__ == "__main__":
    trace_id = step_1_find_failed_trace()
    error_text = step_2_break_the_client()
    step_3_ask_orqi(trace_id, error_text)
    print(f"\nopen {settings.base_url}/traces and search one of the ids above")
