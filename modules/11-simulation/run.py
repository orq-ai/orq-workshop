"""Module 11 starter: simulate customers against the refund agent.

Hand-written test transcripts go stale the day the prompt changes. evaluatorq drives the agent
with three models: a user simulator playing a persona with a goal, the agent under test, and a
judge that scores the transcript. Every simulator and judge call routes through the orq router,
so it is traced and budgeted like any other call. Three steps: simulate() the local agent,
generate_and_simulate() personas from a one-line description, and simulate() the managed agent
twice (built-in "agent:<key>" target, then an AgentTarget adapter that runs the tools).

Fill in the TODOs. The script runs as is; a step with a TODO left prints what is missing.
The solution is in solution/run.py (with refund_target.py, the AgentTarget adapters).
Run it with `uv run python modules/11-simulation/run.py`.
"""

# isort: skip_file
# app.refund_agent.config must load .env before any evaluatorq import (it reads ORQ_API_KEY at import time)
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LOGURU_LEVEL", "INFO")  # evaluatorq logs every turn at DEBUG

from app.refund_agent.agent import chat  # loads .env before evaluatorq reads ORQ_API_KEY
from app.refund_agent.config import settings

from evaluatorq.contracts import LLMCallConfig, Message
from evaluatorq.simulation import simulate
from evaluatorq.simulation.types import (
    CommunicationStyle,
    Criterion,
    Persona,
    Scenario,
    StartingEmotion,
)
from openai import AsyncOpenAI

ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)
SIM_LLM = LLMCallConfig(model=settings.judge_model, client=ROUTER)  # user simulator + judge, traced like any call


async def local_agent(messages: list[Message]) -> str:
    """The agent under test: replay the transcript through chat() each turn (Factor 12)."""
    history = [{"role": message.role, "content": str(message.content)} for message in messages[:-1]]
    result = await asyncio.to_thread(chat, str(messages[-1].content), history)
    return result.text


PERSONAS = [
    Persona(
        name="Impatient repeat buyer",
        patience=0.2,
        assertiveness=0.9,
        politeness=0.3,
        technical_level=0.4,
        communication_style=CommunicationStyle.terse,
        background="Buys often, expects instant refunds",
    ),
    # TODO: a second persona (polite first-time customer)
]
SCENARIOS = [
    Scenario(
        name="In-window refund ord_a1",
        goal="Get order ord_a1 refunded because it was the wrong colour",
        context="ord_a1 (Desk lamp Nord, EUR 24.99) was delivered 3 days ago",
        starting_emotion=StartingEmotion.neutral,
        criteria=[
            Criterion(
                description="Agent states the refunded amount as EUR 24.99", type="must_happen"
            )
        ],
    ),
    # TODO: a post-window scenario on ord_a3 (45 days old) with a must_not_happen criterion.
    # The judge reads the transcript only: criteria must be visible in the assistant's words.
]


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


# ── Step 1 · Simulate two customers against the local agent ──
# Personas times scenarios, up to four turns each. When the post-window scenario is in, read its
# rows before you call them failures: the goal was an out-of-window refund, so an agent that
# refuses fails the goal and passes the must_not_happen criterion. Gate on the criterion.
async def step_1_simulate_local() -> None:
    print("── Step 1 · Simulate two customers against the local agent ──")
    print(f"personas : {', '.join(p.name for p in PERSONAS)}")
    print(f"scenarios: {', '.join(s.name for s in SCENARIOS)}")
    print("turns    : max 4 per conversation")
    if len(PERSONAS) < 2:
        print("TODO     : add the polite first-time customer persona, then rerun")
    if len(SCENARIOS) < 2:
        print("TODO     : add the post-window ord_a3 scenario with a must_not_happen criterion, then rerun")
    results = await simulate(
        evaluation_name=settings.key("sim-local"),
        target=local_agent,
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
# agent. Generated cases are a starting point: check the scenario against the order fixture.
async def step_2_generate() -> None:
    # TODO: generate_and_simulate(agent_description=..., num_personas=3, num_scenarios=1, max_turns=3, target=local_agent, llm_config=SIM_LLM)
    print("── Step 2 · Let the library invent the personas ───────")
    print("TODO     : fill in generate_and_simulate() with 3 personas, 1 scenario, max 3 turns, then rerun")


# ── Step 3 · The managed agent, twice ──
# The built-in "agent:<key>" target cannot run the agent's function tools, so the answer comes
# back empty. An AgentTarget that executes the function_call items fixes the harness.
async def step_3_managed() -> None:
    # TODO: simulate(target=f"agent:{settings.key('refund-agent')}", ...) and read the assistant text: it is empty,
    #       the built-in target stubs the function_call items. Then wrap orq.responses.create in an AgentTarget
    #       that executes them (see solution/refund_target.py, ManagedRefundTarget) and simulate again.
    print("── Step 3 · The managed agent, twice ──────────────────")
    print("TODO     : simulate the managed agent with the built-in target, then with an AgentTarget that runs its tools, then rerun")


if __name__ == "__main__":
    settings.require_key()
    asyncio.run(step_1_simulate_local())
    asyncio.run(step_2_generate())
    asyncio.run(step_3_managed())
