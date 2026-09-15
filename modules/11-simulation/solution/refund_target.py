"""AgentTarget adapters for evaluatorq: the refund agent as something a simulator can talk to.

evaluatorq's simulation and red-team loops drive a *target*: anything with
`respond(messages) -> AgentResponse` and `new()` (a fresh instance per conversation). A plain
callable works for the simplest case; these two classes exist because the refund agent needs
more than that:

- `LocalRefundTarget` wraps the in-process agent (`app.refund_agent.agent.chat`) with a chosen
  instruction file (`fixed` or `vulnerable`). Factor 12: `run_turn` is a reducer, so replaying
  the transcript each turn is enough state. It also records which refunds really went through,
  a ground truth the text-only judge cannot see (module 16 reads it).
- `ManagedRefundTarget` wraps the managed agent through `orq.responses.create(model="agent/<key>")`
  and executes the `function_call` items itself. The built-in `agent:<key>` target answers
  pending tool calls with an error stub, which is fine for a server-executed agent but not for
  one whose tools run on the caller's side (module 11 step 3 shows the difference).

Imported by modules/11-simulation/solution/run.py and modules/16-red-teaming; keep the class
names, constructor arguments and `REFUNDS_ISSUED` as they are.
"""

from __future__ import annotations

import asyncio
import json

from evaluatorq.contracts import AgentTarget, Message
from evaluatorq.redteam.contracts import AgentContext, AgentResponse, TextOutputItem, ToolInfo

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.tools import TOOL_SCHEMAS, OrderStore, dispatch

# Ground truth the judge cannot see: refunds that really went through, per instruction variant.
REFUNDS_ISSUED: dict[str, list[str]] = {"vulnerable": [], "fixed": []}
# ord_a4 is already refunded in the fixture; it must not count as "issued during the run".
_PRE_REFUNDED = {order["id"] for order in OrderStore().orders.values() if order["refunded"]}
MAX_TOOL_ROUNDS = 6  # a refund turn needs at most lookup → policy → refund, with room for retries

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


class ManagedRefundTarget(AgentTarget):
    """The managed agent through the Responses API, with its function_call items executed here (module 08's loop)."""

    def __init__(self, agent_key: str = "ws-refund-agent") -> None:
        super().__init__()
        self.agent_key = agent_key
        self.name = agent_key
        self.orq = make_orq()
        self.store = OrderStore()
        self.prev = None  # previous_response_id: the server keeps the transcript, we keep the pointer

    def new(self) -> ManagedRefundTarget:
        """A fresh store and a fresh conversation on the server side."""
        return type(self)(self.agent_key)

    async def respond(self, messages: list[Message]) -> AgentResponse:
        """Send the newest user message, run every function_call locally, continue until the agent answers in words."""
        response = await asyncio.to_thread(
            self.orq.responses.create,
            model=f"agent/{self.agent_key}",
            input=_last_text(messages),
            previous_response_id=self.prev,
        )
        for _ in range(MAX_TOOL_ROUNDS):
            payload = response.model_dump(exclude_none=True)
            self.prev = payload["id"]
            output_items = payload.get("output", [])
            calls = [item for item in output_items if item.get("type") == "function_call"]
            if not calls:
                text = next(
                    (item["content"][0].get("text", "") for item in output_items if item.get("content")),
                    "",
                )
                return AgentResponse(
                    output=[TextOutputItem(text=text)],
                    response_id=payload["id"],
                    trace_id=(payload.get("telemetry") or {}).get("trace_id"),
                )
            tool_outputs = [
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(
                        dispatch(self.store, call["name"], json.loads(call["arguments"] or "{}"))
                    ),
                }
                for call in calls
            ]
            response = await asyncio.to_thread(
                self.orq.responses.create,
                model=f"agent/{self.agent_key}",
                input=tool_outputs,
                previous_response_id=self.prev,
            )
        raise RuntimeError("tool loop did not converge")
