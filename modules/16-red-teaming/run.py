"""Module 16 starter: red team the vulnerable and the fixed refund prompt side by side.

Fill the TODOs. The solution is in solution/run.py; the attack file is solution/static_attacks.json;
the AgentTarget adapters come from modules/11-simulation/solution/refund_target.py.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "INFO")

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
    attacker=LLMCallConfig(model=settings.model, client=ROUTER),
    evaluator=LLMCallConfig(model=settings.judge_model, client=ROUTER),
)


async def step_1_red_team() -> None:
    print("[1] red_team() vulnerable vs fixed, static")
    report = await red_team(
        [LocalRefundTarget("vulnerable"), LocalRefundTarget("fixed")],
        mode="static",
        dataset=str(DATASET),
        categories=["LLM01", "LLM07"],
        max_static_datapoints=4,
        max_turns=2,
        llm_config=LLM,
        name=settings.key("redteam-local"),
        recommendations=False,
        generate_executive_summary=False,
    )
    print(f"    overall resistance_rate={report.summary.resistance_rate:.0%}")
    # TODO: group report.results by r.agent.key and print a resistance rate per target, plus every r.vulnerable attack
    # TODO: add categories ASI01 and ASI02 (max_static_datapoints=8) and compare
    # TODO: print REFUNDS_ISSUED next to the judge's verdicts: which refunds really went through?


def step_2_cli() -> None:
    # TODO: subprocess: uv run eq redteam run -t agent:ws-refund-agent-vulnerable --mode static --dataset <DATASET>
    #       --max-static-datapoints 4 --max-turns 2 --evaluator-model ... --attack-model ... -y -q ; print the exit code
    print("[2] TODO eq redteam run")


if __name__ == "__main__":
    settings.require_key()
    asyncio.run(step_1_red_team())
    step_2_cli()
