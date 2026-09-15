"""Module 16: red team the vulnerable and the fixed refund prompt side by side.

Module 11 asked "does the agent serve customers"; this one asks "what can a customer make it
do". evaluatorq's red team drives the agent with an attacker model instead of a persona and
scores each transcript against an OWASP category instead of a goal. The attacker and the judge
route through the orq router, so they are traced and budgeted like the agent itself. Static mode
replays a fixed attack file, so the attack side is deterministic: same file, same order. The
targets come from module 11 (solution/refund_target.py): one AgentTarget contract, two agents.
Two steps: red_team() the vulnerable and the fixed LOCAL agent (static, 4 OWASP categories,
8 attacks), then the same red team from the CLI against the managed vulnerable agent.

Run it with `uv run python modules/16-red-teaming/solution/run.py` (or `make m16`), about three
minutes; `--only=1,2` picks steps.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "INFO")  # evaluatorq logs every turn at DEBUG

from app.refund_agent.config import settings  # loads .env before evaluatorq reads ORQ_API_KEY

import evaluatorq.redteam.runner as _redteam_runner
from evaluatorq.contracts import LLMCallConfig
from evaluatorq.redteam import red_team
from evaluatorq.redteam.contracts import LLMConfig
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "11-simulation" / "solution"))
from refund_target import REFUNDS_ISSUED, LocalRefundTarget

# red_team() has no public path/project param: its internal upload always calls
# send_results_to_orq without `path`, which drops the Experiment in the workspace's
# Default project instead of <project>/workshop. Patch the one call site.
_orig_send_results_to_orq = _redteam_runner.send_results_to_orq


async def _send_results_to_orq_scoped(*args: object, **kwargs: object):
    """The library's upload with `path` filled in, so the Experiment lands in <project>/workshop."""
    kwargs.setdefault("path", settings.path)
    return await _orig_send_results_to_orq(*args, **kwargs)


_redteam_runner.send_results_to_orq = _send_results_to_orq_scoped

# Static mode replays a fixed attack file. evaluatorq's default file lives on HuggingFace and needs
# huggingface-hub; this local one has 2 attacks per category, all aimed at the refund agent.
DATASET = Path(__file__).parent / "static_attacks.json"
CATEGORIES = ["LLM01", "LLM07", "ASI01", "ASI02"]  # prompt injection, prompt leakage, goal hijack, tool misuse
CLI_REPORT = "/tmp/ws-redteam-cli.json"
CLI_TAIL_LINES = 34  # the summary tables at the end of the CLI output; the rest is progress noise

ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)


# ── Step 1 · Red team the vulnerable and the fixed prompt side by side ──
# Two LocalRefundTargets over chat(..., instructions=vulnerable | fixed), the same eight static
# attacks against each. The OWASP judge reads the transcript text and does not know the refund
# policy; the order store does. So the step prints both: what the judge flagged, and which
# refunds really went through (REFUNDS_ISSUED). They disagree more often than you would like.
async def step_1_red_team() -> None:
    print("── Step 1 · Red team the vulnerable and the fixed prompt ──")
    print(f"attacks  : static, {', '.join(CATEGORIES)}, 8 datapoints, max 2 turns")
    print(f"dataset  : {DATASET.name}")
    report = await red_team(
        [LocalRefundTarget("vulnerable"), LocalRefundTarget("fixed")],
        mode="static",
        dataset=str(DATASET),
        categories=CATEGORIES,
        max_static_datapoints=8,
        max_turns=2,
        llm_config=LLMConfig(
            attacker=LLMCallConfig(model=settings.model, client=ROUTER),
            evaluator=LLMCallConfig(model=settings.judge_model, client=ROUTER),
        ),
        name=settings.key("redteam-local"),
        recommendations=False,
        generate_executive_summary=False,
        datapoint_parallelism=4,
    )

    results_by_target: dict[str, list] = defaultdict(list)
    for result in report.results:
        results_by_target[getattr(result.agent, "key", None) or str(result.agent)].append(result)
    for target, results in results_by_target.items():
        evaluated = [result for result in results if result.error is None]
        vulnerable = sum(bool(result.vulnerable) for result in evaluated)
        resistance = 1 - vulnerable / len(evaluated) if evaluated else float("nan")
        print(f"target   : {target}, {len(results)} attacks, {vulnerable} judged vulnerable, resistance {resistance:.0%}")
        for result in evaluated:
            if result.vulnerable:
                opening = str(result.messages[0].content)[:70]
                print(f"vuln     : {result.attack.category} {result.attack.vulnerability}: {opening!r}")
    print(f"overall  : resistance {report.summary.resistance_rate:.0%}, {report.summary.total_errors} errors")
    # The OWASP judge reads text and does not know the refund policy. The order store does.
    refunds = "; ".join(f"{variant}: {', '.join(orders) or 'none'}" for variant, orders in REFUNDS_ISSUED.items())
    print(f"refunds  : {refunds} (really issued during the attacks)")
    print(f"report   : {report.experiment_url}")
    print("next     : open the report; compare each vuln line with the refunds line: the judge reads text, the store reads the tool")


# ── Step 2 · The same gate from the CLI ──
# `eq redteam run` against the managed vulnerable agent. The built-in `agent:` target cannot
# execute your function tools, so attacks the agent answers with a tool call come back empty and
# the judge abstains; --min-evaluation-coverage 0 lets the report print instead of failing on
# coverage. The exit code is what CI gates on (module 12).
def step_2_cli() -> None:
    cmd = [
        "uv",
        "run",
        "eq",
        "redteam",
        "run",
        "-t",
        f"agent:{settings.key('refund-agent-vulnerable')}",
        "--mode",
        "static",
        "--dataset",
        str(DATASET),
        "--max-static-datapoints",
        "4",
        "--max-turns",
        "2",
        # the built-in agent: target cannot run our tools; attacks the agent answers with a
        # function_call come back empty and the judge abstains. Warn instead of failing on those.
        "--min-evaluation-coverage",
        "0",
        "--evaluator-model",
        settings.judge_model,
        "--attack-model",
        settings.model,
        "--no-recommendations",
        "--no-executive-summary",
        "--save",
        "final",
        "--report",
        CLI_REPORT,
        "-y",
        "-q",
    ]
    print("── Step 2 · The same gate from the CLI ────────────────")
    print(f"command  : {' '.join(cmd)}")
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    lines = [
        line
        for line in (completed.stdout + completed.stderr).splitlines()
        if line.strip() and "Breakdown" not in line and "Top Vulnerable" not in line
    ]
    print("\n".join("  " + line for line in lines[-CLI_TAIL_LINES:]))
    print(f"exit     : {completed.returncode} ({'gate passed' if completed.returncode == 0 else 'gate failed'})")
    print(f"next     : read Eval Coverage before ASR; the full report is in {CLI_REPORT}")


if __name__ == "__main__":
    settings.require_key()
    # --only=1,2 runs a subset of steps; default is both.
    only = {
        step for arg in sys.argv[1:] if arg.startswith("--only") for step in arg.split("=")[-1].split(",")
    } or {"1", "2"}
    if "1" in only:
        asyncio.run(step_1_red_team())
    if "2" in only:
        step_2_cli()
