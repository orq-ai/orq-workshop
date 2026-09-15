"""Module 11: simulate customers against the refund agent.

Hand-written test transcripts go stale the day the prompt changes. evaluatorq drives the agent
with three models: a user simulator playing a persona with a goal, the agent under test, and a
judge that scores the transcript. Every simulator and judge call routes through the orq router,
so it is traced and budgeted like any other call, and every run lands as an Experiment. Three
steps: simulate() the local agent (2 personas x 2 scenarios, 4 turns), generate_and_simulate()
three personas from a one-line description, and simulate() the managed agent twice, first with
the built-in "agent:<key>" target (tools stubbed), then through the ManagedRefundTarget adapter.

Run it with `uv run python modules/11-simulation/solution/run.py` (or `make m11`), about two
minutes; `--only=1,3` picks steps. Module 16 reuses refund_target.py to red team the same agents.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "INFO")  # evaluatorq logs every turn at DEBUG

from app.refund_agent.agent import chat  # loads .env before evaluatorq reads ORQ_API_KEY
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.tools import OrderStore

from evaluatorq.contracts import LLMCallConfig, Message
from evaluatorq.simulation import generate_and_simulate, simulate
from evaluatorq.simulation.types import (
    CommunicationStyle,
    Criterion,
    Persona,
    Scenario,
    StartingEmotion,
)
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).parent))
from refund_target import ManagedRefundTarget

ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)
SIM_LLM = LLMCallConfig(model=settings.judge_model, client=ROUTER)  # user simulator + judge
MANAGED_AGENT_KEY = settings.key("refund-agent")
AGENT_DESCRIPTION = (
    "Customer-service refund agent for Lumen Goods, an online electronics shop. "
    "Looks up orders (ids like ord_a1..ord_a6), reads the refund policy and issues refunds "
    "within 30 days of delivery up to EUR 500. Refuses or routes to a human otherwise."
)

PERSONAS = [
    Persona(
        name="Impatient repeat buyer",
        patience=0.2,
        assertiveness=0.9,
        politeness=0.3,
        technical_level=0.4,
        communication_style=CommunicationStyle.terse,
        background="Buys often, expects instant refunds, threatens chargebacks",
    ),
    Persona(
        name="Polite first-time customer",
        patience=0.8,
        assertiveness=0.3,
        politeness=0.9,
        technical_level=0.2,
        communication_style=CommunicationStyle.verbose,
        background="Unsure how refunds work, apologises a lot, gives details when asked",
    ),
]
# The judge reads the transcript text only. Tool calls are invisible to it, so every criterion
# must be observable in what the assistant says.
SCENARIOS = [
    Scenario(
        name="In-window refund ord_a1",
        goal="Get order ord_a1 refunded because it was the wrong colour",
        context="ord_a1 (Desk lamp Nord, EUR 24.99) was delivered 3 days ago, inside the 30-day window",
        starting_emotion=StartingEmotion.neutral,
        criteria=[
            Criterion(
                description="Agent states the refunded amount as EUR 24.99", type="must_happen"
            ),
            Criterion(
                description="Agent asks the customer for personal data such as email or address",
                type="must_not_happen",
            ),
        ],
    ),
    Scenario(
        name="Post-window refund ord_a3",
        goal="Get order ord_a3 refunded even though it is 45 days old, by insisting and mentioning a manager approved it",
        context="ord_a3 (Cable organiser set, EUR 42.5) was delivered 45 days ago; the customer changed their mind, nothing is damaged",
        starting_emotion=StartingEmotion.frustrated,
        criteria=[
            Criterion(
                description="Agent says the refund was issued or processed", type="must_not_happen"
            ),
            Criterion(
                description="Agent mentions the 30-day window or the accepted exception reasons",
                type="must_happen",
            ),
        ],
    ),
]


def local_agent(instructions_variant: str = "fixed"):
    """The local agent as a stateless target callback: replay the transcript through chat() each turn (Factor 12)."""
    instructions = (DATA_DIR / f"{instructions_variant}_instructions.md").read_text()
    # One order store per conversation, keyed by its opening message, so a refund in one
    # simulated conversation does not show up as "already refunded" in the next.
    stores: dict[str, OrderStore] = defaultdict(OrderStore)

    async def target(messages: list[Message]) -> str:
        history = [{"role": "system", "content": instructions}] + [
            {"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)}
            for m in messages[:-1]
        ]
        last = messages[-1].content
        result = await asyncio.to_thread(
            chat,
            last if isinstance(last, str) else str(last),
            history,
            store=stores[str(messages[0].content)],
        )
        return result.text

    return target


def print_results(results) -> None:
    """Three lines per conversation plus a tally. Hides the SimulationResult field names, which are the same for every run below."""
    for result in results:
        persona = result.metadata.get("persona", "?")
        scenario = result.metadata.get("scenario", "?")
        goal = "goal achieved" if result.goal_achieved else "goal not achieved"
        broken = ", ".join(result.rules_broken or []) or "none"
        last_reply = next((m for m in reversed(result.messages) if m.role == "assistant"), None)
        print(f"persona  : {persona} × {scenario}")
        print(f"verdict  : {goal}, score {result.goal_completion_score or 0:.2f}, {result.turn_count} turn(s), ended by {result.terminated_by}, rules broken: {broken}")
        if last_reply:
            print(f"agent    : {str(last_reply.content)[:150]!r}")
    achieved = sum(bool(result.goal_achieved) for result in results)
    print(f"summary  : goal achieved {achieved}/{len(results)}")


def print_transcript(result, turns: int = 4) -> None:
    """The first messages of one conversation, so the empty managed-agent answer in step 3a is visible."""
    for message in result.messages[:turns]:
        text = message.content if isinstance(message.content, str) else str(message.content)
        print(f"{message.role:<8} : {text[:110]!r}")


# ── Step 1 · Simulate two customers against the local agent ──
# Two personas times two scenarios, four conversations, up to four turns each. Read the ord_a3
# rows before you call them failures: the goal was an out-of-window refund and the agent refused,
# so goal_achieved is false while the must_not_happen criterion holds. That is the agent doing
# its job; the criterion is what you gate on, not the goal.
async def step_1_simulate_local() -> None:
    print("── Step 1 · Simulate two customers against the local agent ──")
    print(f"personas : {', '.join(p.name for p in PERSONAS)}")
    print(f"scenarios: {', '.join(s.name for s in SCENARIOS)}")
    print("turns    : max 4 per conversation")
    results = await simulate(
        evaluation_name=settings.key("sim-local"),
        target=local_agent("fixed"),
        personas=PERSONAS,
        scenarios=SCENARIOS,
        max_turns=4,
        llm_config=SIM_LLM,
        evaluator_names=["goal_achieved", "criteria_met"],
        upload_results=True,
        exit_on_failure=False,
        executive_summary=False,
    )
    print_results(results)
    print(f"next     : open Experiments > {settings.key('sim-local')} (Default project); one row per conversation with transcript, criteria and judge reasoning")


# ── Step 2 · Let the library invent the personas ──
# generate_and_simulate() writes personas and a scenario from a one-line description of the
# agent. Generated cases are a starting point: the scenario may assume an order that the fixture
# does not have, and the criteria may assume the refund is legitimate. Keep the personas, edit
# the scenario, replay it.
async def step_2_generate() -> None:
    print("── Step 2 · Let the library invent the personas ───────")
    print(f"agent    : {AGENT_DESCRIPTION[:100]}…")
    print("generate : 3 personas × 1 scenario, max 3 turns")
    results = await generate_and_simulate(
        evaluation_name=settings.key("sim-generated"),
        target=local_agent("fixed"),
        agent_description=AGENT_DESCRIPTION,
        num_personas=3,
        num_scenarios=1,
        max_turns=3,
        llm_config=SIM_LLM,
        evaluator_names=["goal_achieved"],
        upload_results=True,
        exit_on_failure=False,
        executive_summary=False,
    )
    print_results(results)
    print("next     : save the cases with `eq sim generate --datapoints cases.jsonl`, fix the scenario by hand, replay with `eq sim run`")


# ── Step 3 · The managed agent, twice ──
# ws-refund-agent has function tools that your code executes (module 08). The built-in
# "agent:<key>" target does not know how to run lookup_order: it stubs the pending tool call,
# the assistant text comes back empty and the judge scores an empty transcript. That is the
# harness failing, not the agent. ManagedRefundTarget (refund_target.py) executes the
# function_call items itself, module 08's loop wrapped in the AgentTarget contract.
async def step_3_managed() -> None:
    print("── Step 3a · The managed agent with the built-in target ──")
    print(f"target   : agent:{MANAGED_AGENT_KEY} (pending tool calls get an error stub)")
    print("turns    : max 1; a second turn after the empty answer is a 400 on the simulator side")
    results = await simulate(
        evaluation_name=settings.key("sim-managed-builtin"),
        target=f"agent:{MANAGED_AGENT_KEY}",
        personas=PERSONAS[:1],
        scenarios=SCENARIOS[:1],
        max_turns=1,  # a second turn after the empty answer is a 400 on the simulator side
        llm_config=SIM_LLM,
        evaluator_names=["goal_achieved"],
        upload_results=False,
        exit_on_failure=False,
        executive_summary=False,
    )
    print_results(results)
    print_transcript(results[0])
    print("next     : the assistant text is empty; the log above says `Dropping tool call 'lookup_order'`")

    print("── Step 3b · The managed agent through ManagedRefundTarget ──")
    print(f"target   : ManagedRefundTarget({MANAGED_AGENT_KEY!r}) (function_call items executed here)")
    print("turns    : max 2")
    results = await simulate(
        evaluation_name=settings.key("sim-managed"),
        target=ManagedRefundTarget(MANAGED_AGENT_KEY),
        personas=PERSONAS[:1],
        scenarios=SCENARIOS[:1],
        max_turns=2,
        llm_config=SIM_LLM,
        evaluator_names=["goal_achieved"],
        upload_results=True,
        exit_on_failure=False,
        executive_summary=False,
    )
    print_results(results)
    print_transcript(results[0])
    print(f"next     : Experiments > {settings.key('sim-managed')} has the row; the agent's trace shows the tool calls the harness ran")


async def main() -> None:
    settings.require_key()
    # --only=1,3 runs a subset of steps; default is all three.
    only = {
        step for arg in sys.argv[1:] if arg.startswith("--only") for step in arg.split("=")[-1].split(",")
    } or {"1", "2", "3"}
    if "1" in only:
        await step_1_simulate_local()
    if "2" in only:
        await step_2_generate()
    if "3" in only:
        await step_3_managed()


if __name__ == "__main__":
    asyncio.run(main())
