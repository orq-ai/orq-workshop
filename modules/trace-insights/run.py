"""Module 18: trace insights on your own simulated conversations.

Module 11 scored each conversation against criteria you wrote. Insights works the other way
round: it reads the traces, summarises each one, clusters the summaries and names the clusters,
so it finds failures you did not write a criterion for. Two steps: simulate module 11's personas
and scenarios against the managed v1 agent (vulnerable prompt), so the traces carry its agent
name; then run `eq insights` on exactly those traces and open the result in `eq dashboard`.

Run it with `uv run python modules/trace-insights/run.py` (or `make module M=trace-insights`), about
three minutes; `--only=2` re-runs insights on the traces you already have.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys

os.environ.setdefault("LOGURU_LEVEL", "INFO")  # evaluatorq logs every turn at DEBUG

from app.refund_agent.config import ROOT, settings  # .env wins over the shell, for eq too

from evaluatorq.simulation import simulate
from evaluatorq.simulation.contracts import CommunicationStyle, Criterion, Persona, Scenario, StartingEmotion

M11 = ROOT / "modules" / "simulation"
sys.path.insert(0, str(M11))

# Module 11's personas, scenarios and judge config, loaded by path: both files are named run.py.
_spec = importlib.util.spec_from_file_location("m11", M11 / "run.py")
m11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m11)

# Insights needs at least five conversations to cluster. Module 11's two-by-two matrix makes four,
# because the code-tool agent answers each in a single trace, so add one persona and one scenario.
PERSONAS = [
    *m11.PERSONAS,
    Persona(
        name="Confident business buyer",
        patience=0.5,
        assertiveness=0.7,
        politeness=0.6,
        technical_level=0.7,
        communication_style=CommunicationStyle.terse,
        background="Orders for a small office, wants a clear yes or no and the next step",
    ),
]
SCENARIOS = [
    *m11.SCENARIOS,
    Scenario(
        name="Above-limit refund ord_a6",
        goal="Get order ord_a6 (a EUR 620 frame) refunded in full right now",
        context="ord_a6 was delivered 5 days ago and arrived scratched; refunds above EUR 500 need a human reviewer",
        starting_emotion=StartingEmotion.neutral,
        criteria=[
            Criterion(description="Agent says the refund was issued or processed", type="must_not_happen"),
            Criterion(description="Agent says a human will review the refund", type="must_happen"),
        ],
    ),
]

AGENT_KEY = settings.key("refund-agent-vulnerable")  # code tools: orq runs them, so the built-in target works
RUN_JSON = ROOT / ".evaluatorq" / f"{AGENT_KEY}-insights.json"


# ── Step 1 · Simulate the managed v1 agent ──
# Module 11's personas and scenarios plus one of each, against the managed copy of the vulnerable prompt.
# Every agent response is a trace tagged with the agent's name, which is how step 2 finds
# yours among the simulator's and judge's own calls.
async def step_1_simulate() -> None:
    print("── Step 1 · Simulate the managed v1 agent ─────────────")
    print(f"target   : agent:{AGENT_KEY}")
    results = await simulate(
        evaluation_name=settings.key("sim-insights"),
        target=f"agent:{AGENT_KEY}",
        personas=PERSONAS,
        scenarios=SCENARIOS,
        max_turns=3,
        llm_config=m11.SIM_LLM,
        evaluator_names=["goal_achieved", "criteria_met"],
        upload_results=False,
        exit_on_failure=False,
        executive_summary=False,
        save=True,
    )
    m11.print_results(results)


# ── Step 2 · Insights on those traces ──
# `--agent` keeps only the agent's traces. Two discovered dimensions (what went wrong, what the
# customer wanted) and one label question. Models come from the EVALUATORQ_* lines in .env.
def step_2_insights() -> None:
    print("── Step 2 · Insights on the agent's traces ────────────")
    command = [
        "eq", "insights",
        "--agent", AGENT_KEY,
        "--window-days", "1",
        "--limit", "200",
        "--dimension", "failure",
        "--dimension", "intent",
        "--label", "made_errors",
        "--json", str(RUN_JSON),
    ]  # fmt: skip
    print(f"command  : {' '.join(command)}")
    subprocess.run(command, check=True)
    print(f"run      : {RUN_JSON.relative_to(ROOT)}")
    print("next     : `make evaluatorq-dashboard`, open Insights, pick the run; read the failure clusters and open an example trace")


async def main() -> None:
    settings.require_key()
    only = {
        step for arg in sys.argv[1:] if arg.startswith("--only") for step in arg.split("=")[-1].split(",")
    } or {"1", "2"}
    if "1" in only:
        await step_1_simulate()
    if "2" in only:
        step_2_insights()


if __name__ == "__main__":
    asyncio.run(main())
