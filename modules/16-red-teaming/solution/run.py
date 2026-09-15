"""Module 16 solution: red team the vulnerable and the fixed refund prompt side by side.

Steps (pick with --only 1,2):
  1. red_team() vulnerable vs fixed LOCAL agent, static mode, 4 OWASP categories, 8 attacks
  2. the same red team from the CLI: eq redteam run -t agent:ws-refund-agent-vulnerable --mode static

The attacker and the judge route through the orq router, so they are traced and budgeted like
the agent itself. Static mode is deterministic on the attack side: same file, same order.
The targets come from module 11 (solution/refund_target.py): one AgentTarget contract, two agents.
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
    kwargs.setdefault("path", settings.path)
    return await _orig_send_results_to_orq(*args, **kwargs)


_redteam_runner.send_results_to_orq = _send_results_to_orq_scoped

# Static mode replays a fixed attack file. evaluatorq's default file lives on HuggingFace and needs
# huggingface-hub; this local one has 2 attacks per category, all aimed at the refund agent.
DATASET = Path(__file__).parent / "static_attacks.json"

ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)


async def step_1_red_team() -> None:
    print(
        "[1] red_team() vulnerable vs fixed local agent, static, LLM01 LLM07 ASI01 ASI02, 8 datapoints"
    )
    report = await red_team(
        [LocalRefundTarget("vulnerable"), LocalRefundTarget("fixed")],
        mode="static",
        dataset=str(DATASET),
        categories=["LLM01", "LLM07", "ASI01", "ASI02"],
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
    per: dict[str, list] = defaultdict(list)
    for r in report.results:
        per[getattr(r.agent, "key", None) or str(r.agent)].append(r)
    for agent, rs in per.items():
        evaluated = [r for r in rs if r.error is None]
        vuln = sum(bool(r.vulnerable) for r in evaluated)
        rate = 1 - vuln / len(evaluated) if evaluated else float("nan")
        print(f"    {agent:24s} attacks={len(rs)} judged vulnerable={vuln} resistance={rate:.0%}")
        for r in evaluated:
            if r.vulnerable:
                print(
                    f"        VULN {r.attack.category} {r.attack.vulnerability}: {str(r.messages[0].content)[:70]!r}"
                )
    print(
        f"    overall resistance_rate={report.summary.resistance_rate:.0%} errors={report.summary.total_errors}"
    )
    # The OWASP judge reads text and does not know the refund policy. The order store does.
    print(f"    refunds really issued during the attacks: {dict(REFUNDS_ISSUED)}")
    print(f"    experiment: {report.experiment_url}")


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
        "/tmp/ws-redteam-cli.json",
        "-y",
        "-q",
    ]
    print("[2] " + " ".join(cmd))
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    lines = [
        l
        for l in (out.stdout + out.stderr).splitlines()
        if l.strip() and "Breakdown" not in l and "Top Vulnerable" not in l
    ]
    print("\n".join("    " + l for l in lines[-34:]))
    print(f"    exit code {out.returncode}")


if __name__ == "__main__":
    settings.require_key()
    only = {
        s for a in sys.argv[1:] if a.startswith("--only") for s in a.split("=")[-1].split(",")
    } or {"1", "2"}
    if "1" in only:
        asyncio.run(step_1_red_team())
    if "2" in only:
        step_2_cli()
