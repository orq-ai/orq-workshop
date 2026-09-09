"""Module 11 starter: simulate customers against the refund agent, then red team it.

Fill the TODOs. The solution is in solution/run.py (with refund_target.py and static_attacks.json).
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LOGURU_LEVEL", "INFO")

from app.refund_agent.agent import chat  # noqa: E402  (loads .env before evaluatorq reads ORQ_API_KEY)
from app.refund_agent.config import settings
from evaluatorq.contracts import LLMCallConfig, Message
from evaluatorq.simulation import simulate
from evaluatorq.simulation.types import CommunicationStyle, Criterion, Persona, Scenario, StartingEmotion
from openai import AsyncOpenAI

ROUTER = AsyncOpenAI(base_url=settings.router_url, api_key=settings.api_key)
SIM_LLM = LLMCallConfig(model=settings.judge_model, client=ROUTER)  # user simulator + judge, traced like any call


async def local_agent(messages: list[Message]) -> str:
    """The agent under test: replay the transcript through run_turn each turn (Factor 12)."""
    history = [{"role": m.role, "content": str(m.content)} for m in messages[:-1]]
    r = await asyncio.to_thread(chat, str(messages[-1].content), history)
    return r.text


PERSONAS = [
    Persona(name="Impatient repeat buyer", patience=0.2, assertiveness=0.9, politeness=0.3, technical_level=0.4,
            communication_style=CommunicationStyle.terse, background="Buys often, expects instant refunds"),
    # TODO: a second persona (polite first-time customer)
]
SCENARIOS = [
    Scenario(name="In-window refund ord_a1", goal="Get order ord_a1 refunded because it was the wrong colour",
             context="ord_a1 (Desk lamp Nord, EUR 24.99) was delivered 3 days ago", starting_emotion=StartingEmotion.neutral,
             criteria=[Criterion(description="Agent states the refunded amount as EUR 24.99", type="must_happen")]),
    # TODO: a post-window scenario on ord_a3 (45 days old) with a must_not_happen criterion.
    # The judge reads the transcript only: criteria must be visible in the assistant's words.
]


async def step_1_simulate_local() -> None:
    print("[1] simulate() local agent")
    results = await simulate(
        evaluation_name=settings.key("sim-local"), target=local_agent, personas=PERSONAS, scenarios=SCENARIOS,
        max_turns=4, llm_config=SIM_LLM, evaluator_names=["goal_achieved", "criteria_met"],
        upload_results=True, exit_on_failure=False, executive_summary=False,
    )
    for r in results:
        print(f"    {'PASS' if r.goal_achieved else 'FAIL'} turns={r.turn_count} rules_broken={r.rules_broken or []}")


async def step_2_generate() -> None:
    # TODO: generate_and_simulate(agent_description=..., num_personas=3, num_scenarios=1, max_turns=3, target=local_agent, llm_config=SIM_LLM)
    print("[2] TODO generate_and_simulate")


async def step_4_red_team() -> None:
    # TODO: from evaluatorq.redteam import red_team; targets = AgentTarget subclasses over chat(..., instructions=vulnerable|fixed)
    #       red_team([vuln, fixed], mode="static", dataset="modules/11-simulation-red-team/solution/static_attacks.json",
    #                categories=["LLM01", "LLM07", "ASI01", "ASI02"], llm_config=LLMConfig(attacker=..., evaluator=...))
    print("[4] TODO red_team")


if __name__ == "__main__":
    settings.require_key()
    asyncio.run(step_1_simulate_local())
    asyncio.run(step_2_generate())
    asyncio.run(step_4_red_team())
