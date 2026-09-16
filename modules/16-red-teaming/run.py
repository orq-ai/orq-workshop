"""Module 16 starter: red team the vulnerable and the fixed refund prompt side by side.

An attacker is a simulated user with a worse goal. evaluatorq's red team drives the agent with an
attacker model and scores each transcript against an OWASP category. Static mode replays a fixed
attack file, so the attack side is deterministic. Two steps: red_team() the vulnerable and the
fixed local agent, then the same red team from the CLI.

Fill in the TODOs. The script runs as is; a step with a TODO left prints what is missing.
The solution is in solution/run.py; the attack file is solution/static_attacks.json; the
AgentTarget adapters come from modules/11-simulation/solution/refund_target.py.
Run it with `uv run python modules/16-red-teaming/run.py`.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "INFO")  # evaluatorq logs every turn at DEBUG

from app.refund_agent.config import settings  # loads .env before evaluatorq reads ORQ_API_KEY

from evaluatorq.contracts import LLMCallConfig
from evaluatorq.redteam import red_team
from evaluatorq.redteam.contracts import LLMConfig
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "11-simulation" / "solution"))
from refund_target import LocalRefundTarget

DATASET = Path(__file__).parent / "solution" / "static_attacks.json"
ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)
LLM = LLMConfig(
    attacker=LLMCallConfig(model=settings.model, client=ROUTER),  # writes the attack turns
    evaluator=LLMCallConfig(model=settings.judge_model, client=ROUTER),  # the OWASP judge
)


# ── Step 1 · Red team the vulnerable and the fixed prompt side by side ──
# Two LocalRefundTargets, one per instruction file, the same static attacks against each. The
# judge reads the transcript text only; the order store knows which refunds really went through.
async def step_1_red_team() -> None:
    print("── Step 1 · Red team the vulnerable and the fixed prompt ──")
    categories = ["LLM01", "LLM07"]
    print(f"attacks  : static, {', '.join(categories)}, 4 datapoints, max 2 turns")
    report = await red_team(
        [LocalRefundTarget("vulnerable"), LocalRefundTarget("fixed")],
        mode="static",
        dataset=str(DATASET),
        categories=categories,
        max_static_datapoints=4,
        max_turns=2,
        llm_config=LLM,
        name=settings.key("redteam-local"),
        recommendations=False,
        generate_executive_summary=False,
    )
    print(f"overall  : resistance {report.summary.resistance_rate:.0%}")
    # TODO: group report.results by result.agent.key and print a resistance rate per target, plus every result.vulnerable attack
    print("TODO     : group report.results by target, print a resistance rate per target and every vulnerable attack, then rerun")
    # TODO: add categories ASI01 and ASI02 (max_static_datapoints=8) and compare
    if len(categories) < 4:
        print("TODO     : add ASI01 and ASI02 with max_static_datapoints=8, then rerun and compare")
    # TODO: print REFUNDS_ISSUED next to the judge's verdicts: which refunds really went through?
    print("TODO     : import REFUNDS_ISSUED from refund_target and print it next to the verdicts, then rerun")
    print(f"report   : {report.experiment_url}")


# ── Step 2 · The same gate from the CLI ──
# `eq redteam run` against the managed vulnerable agent; its exit code is what CI gates on.
def step_2_cli() -> None:
    # TODO: subprocess: uv run eq redteam run -t agent:ws-refund-agent-vulnerable --mode static --dataset <DATASET>
    #       --max-static-datapoints 4 --max-turns 2 --evaluator-model ... --attack-model ... -y -q ; print the exit code
    print("── Step 2 · The same gate from the CLI ────────────────")
    print("TODO     : fill in the eq redteam run subprocess and print its exit code, then rerun")


if __name__ == "__main__":
    settings.require_key()
    asyncio.run(step_1_red_team())
    step_2_cli()
