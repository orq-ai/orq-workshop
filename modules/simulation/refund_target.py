"""AgentTarget for the in-process refund agent, the one target evaluatorq cannot provide itself.

evaluatorq's simulation and red-team loops drive a *target*: anything with
`respond(messages) -> AgentResponse` and `new()` (a fresh instance per conversation). Orq-hosted
agents need no class: pass the string `agent:<key>` (the hosted refund agents run their tools in
orq, so the built-in target works as is; the simulation module step 3 shows why the function-tool agent
does not).

`LocalRefundTarget` wraps the in-process agent (`app.refund_agent.agent.chat`) with a chosen
instruction file (`fixed` or `vulnerable`). Factor 12: `run_turn` is a reducer, so replaying the
transcript each turn is enough state. It also records which refunds really went through, a
ground truth the text-only judge cannot see (the red-teaming module reads it).

Imported by modules/red-teaming; keep the class name, constructor arguments and
`REFUNDS_ISSUED` as they are.
"""

from __future__ import annotations

import asyncio

from evaluatorq.contracts import AgentTarget, Message
from evaluatorq.redteam.contracts import AgentContext, AgentResponse, TextOutputItem, ToolInfo

from app.refund_agent.agent import chat
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.tools import TOOL_SCHEMAS, OrderStore

# Ground truth the judge cannot see: refunds that really went through, per instruction variant.
REFUNDS_ISSUED: dict[str, list[str]] = {"vulnerable": [], "fixed": []}
# ord_a4 is already refunded in the fixture; it must not count as "issued during the run".
_PRE_REFUNDED = {order["id"] for order in OrderStore().orders.values() if order["refunded"]}

# The tool schemas in the shape the red-team attacker reads (name, description, parameters).
TOOLS = [
    ToolInfo(
        name=schema["function"]["name"],
        description=schema["function"]["description"],
        parameters=schema["function"]["parameters"],
    )
    for schema in TOOL_SCHEMAS
]


def _last_text(messages: list[Message]) -> str:
    """The newest message as text; evaluatorq may send structured content, the agent wants a string."""
    last = messages[-1].content
    return last if isinstance(last, str) else str(last)


class LocalRefundTarget(AgentTarget):
    """The in-process refund agent under one instruction file, with its own order store per conversation."""

    def __init__(self, variant: str = "fixed") -> None:
        super().__init__()
        self.variant = variant
        self.agent_key = f"local-refund-{variant}"
        self.name = self.agent_key  # the report labels targets by .name
        self.instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
        self.store = OrderStore()
        self.history = []

    def new(self) -> LocalRefundTarget:
        """A fresh store and transcript: evaluatorq calls this once per conversation."""
        return type(self)(self.variant)

    async def get_agent_context(self) -> AgentContext:
        """What the red-team attacker is told about the target: key, instructions, tools, model."""
        return AgentContext(
            key=self.agent_key, instructions=self.instructions, tools=TOOLS, model=settings.model
        )

    async def respond(self, messages: list[Message]) -> AgentResponse:
        """One agent turn on the newest user message; chat() is sync, so it runs in a thread."""
        result = await asyncio.to_thread(
            chat,
            _last_text(messages),
            self.history,
            instructions=self.instructions,
            store=self.store,
        )
        self.history = result.messages
        # Anything refunded in the store since the last turn was issued by this conversation.
        already_counted = _PRE_REFUNDED | set(REFUNDS_ISSUED[self.variant])
        REFUNDS_ISSUED[self.variant] += [
            order["id"]
            for order in self.store.orders.values()
            if order["refunded"] and order["id"] not in already_counted
        ]
        return AgentResponse(output=[TextOutputItem(text=result.text)], trace_id=result.trace_id)

