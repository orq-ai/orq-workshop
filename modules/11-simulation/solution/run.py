"""Module 11 solution: simulate customers against the refund agent.

Steps (pick with --only 1,3):
  1. simulate() the LOCAL agent: 2 personas x 2 scenarios, 4 turns
  2. generate_and_simulate(): 3 generated personas from a one-line description
  3. simulate() the MANAGED agent: built-in "agent:<key>" target (tools stubbed), then the adapter

Every simulator and judge call routes through the orq router, so they are traced and budgeted
like any other call. Module 16 reuses refund_target.py to red team the same agents.
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
from app.refund_agent.config import settings
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
SCENARIOS = [
    # The judge reads the transcript text only. Tool calls are invisible to it, so every criterion must be
    # observable in what the assistant says.
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
    """A stateless callback: replay the transcript through run_turn each turn. Factor 12."""
    from app.refund_agent.config import DATA_DIR

    instructions = (DATA_DIR / f"{instructions_variant}_instructions.md").read_text()
    stores: dict[str, OrderStore] = defaultdict(
        OrderStore
    )  # one store per conversation, keyed by its opening message

    async def target(messages: list[Message]) -> str:
        history = [{"role": "system", "content": instructions}] + [
            {"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)}
            for m in messages[:-1]
        ]
        last = messages[-1].content
        r = await asyncio.to_thread(
            chat,
            last if isinstance(last, str) else str(last),
            history,
            store=stores[str(messages[0].content)],
        )
        return r.text

    return target


def print_results(results) -> None:
    for r in results:
        p, s = r.metadata.get("persona", "?"), r.metadata.get("scenario", "?")
        print(
            f"    {'PASS' if r.goal_achieved else 'FAIL'} score={r.goal_completion_score or 0:.2f} turns={r.turn_count} "
            f"by={r.terminated_by} persona={p!r} scenario={s!r} rules_broken={r.rules_broken or []}"
        )
        last = next((m for m in reversed(r.messages) if m.role == "assistant"), None)
        if last:
            print(f"         agent: {str(last.content)[:150]!r}")
    passed = sum(bool(r.goal_achieved) for r in results)
    print(f"    goal achieved {passed}/{len(results)}")


async def step_1_simulate_local() -> None:
    print("[1] simulate() local agent: 2 personas x 2 scenarios, max_turns=4")
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


async def step_2_generate() -> None:
    print("[2] generate_and_simulate(): 3 generated personas x 1 scenario, max_turns=3")
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


async def step_3_managed() -> None:
    key = settings.key("refund-agent")
    print(
        f"[3a] simulate() managed agent with the built-in target 'agent:{key}' (pending tool calls get an error stub)"
    )
    results = await simulate(
        evaluation_name=settings.key("sim-managed-builtin"),
        target=f"agent:{key}",
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
    for m in results[0].messages[:4]:
        print(
            f"      {m.role:9s} {(m.content if isinstance(m.content, str) else str(m.content))[:110]!r}"
        )
    print(
        "[3b] simulate() managed agent through ManagedRefundTarget (function_call items executed here)"
    )
    results = await simulate(
        evaluation_name=settings.key("sim-managed"),
        target=ManagedRefundTarget(key),
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
    for m in results[0].messages[:4]:
        print(
            f"      {m.role:9s} {(m.content if isinstance(m.content, str) else str(m.content))[:110]!r}"
        )


if __name__ == "__main__":
    settings.require_key()
    only = {
        s for a in sys.argv[1:] if a.startswith("--only") for s in a.split("=")[-1].split(",")
    } or {"1", "2", "3"}
    if "1" in only:
        asyncio.run(step_1_simulate_local())
    if "2" in only:
        asyncio.run(step_2_generate())
    if "3" in only:
        asyncio.run(step_3_managed())
