"""AgentTarget adapters for evaluatorq (simulation and red team).

Two targets, one contract: `respond(messages) -> AgentResponse` and `new()`.

- LocalRefundTarget wraps the in-process agent (`app.refund_agent.agent.chat`) with a
  chosen instruction file. Factor 12: `run_turn` is a reducer, so replaying the transcript
  each turn is enough state.
- ManagedRefundTarget wraps the managed agent through `orq.responses.create(model="agent/<key>")`
  and executes the `function_call` items itself. The built-in `agent:<key>` target answers
  pending tool calls with an error stub, which is fine for a server-executed agent but not
  for one whose tools run on the caller's side.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from evaluatorq.contracts import AgentTarget, Message
from evaluatorq.redteam.contracts import AgentContext, AgentResponse, TextOutputItem, ToolInfo

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.tools import TOOL_SCHEMAS, OrderStore, dispatch

# Ground truth the judge cannot see: refunds that really went through, per instruction variant.
REFUNDS_ISSUED: dict[str, list[str]] = {"vulnerable": [], "fixed": []}
_PRE_REFUNDED = {o["id"] for o in OrderStore().orders.values() if o["refunded"]}  # ord_a4 in the fixture

TOOLS = [ToolInfo(name=t["function"]["name"], description=t["function"]["description"], parameters=t["function"]["parameters"]) for t in TOOL_SCHEMAS]


def _text(messages: list[Message]) -> str:
    return messages[-1].content if isinstance(messages[-1].content, str) else str(messages[-1].content)


class LocalRefundTarget(AgentTarget):
    def __init__(self, variant: str = "fixed") -> None:
        super().__init__()
        self.variant, self.agent_key = variant, f"local-refund-{variant}"
        self.name = self.agent_key  # the report labels targets by .name
        self.instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
        self.store, self.history = OrderStore(), []

    def new(self) -> LocalRefundTarget:
        return type(self)(self.variant)

    async def get_agent_context(self) -> AgentContext:
        return AgentContext(key=self.agent_key, instructions=self.instructions, tools=TOOLS, model=settings.model)

    async def respond(self, messages: list[Message]) -> AgentResponse:
        r = await asyncio.to_thread(chat, _text(messages), self.history, instructions=self.instructions, store=self.store)
        self.history = r.messages
        REFUNDS_ISSUED[self.variant] += [o["id"] for o in self.store.orders.values() if o["refunded"] and o["id"] not in _PRE_REFUNDED | set(REFUNDS_ISSUED[self.variant])]
        return AgentResponse(output=[TextOutputItem(text=r.text)], trace_id=r.trace_id)


class ManagedRefundTarget(AgentTarget):
    def __init__(self, agent_key: str = "ws-refund-agent") -> None:
        super().__init__()
        self.agent_key, self.orq, self.store, self.prev = agent_key, make_orq(), OrderStore(), None
        self.name = agent_key

    def new(self) -> ManagedRefundTarget:
        return type(self)(self.agent_key)

    async def respond(self, messages: list[Message]) -> AgentResponse:
        resp = await asyncio.to_thread(self.orq.responses.create, model=f"agent/{self.agent_key}", input=_text(messages), previous_response_id=self.prev)
        for _ in range(6):
            d = resp.model_dump(exclude_none=True)
            self.prev = d["id"]
            calls = [o for o in d.get("output", []) if o.get("type") == "function_call"]
            if not calls:
                text = next((o["content"][0].get("text", "") for o in d.get("output", []) if o.get("content")), "")
                return AgentResponse(output=[TextOutputItem(text=text)], response_id=d["id"], trace_id=(d.get("telemetry") or {}).get("trace_id"))
            items = [{"type": "function_call_output", "call_id": c["call_id"], "output": json.dumps(dispatch(self.store, c["name"], json.loads(c["arguments"] or "{}")))} for c in calls]
            resp = await asyncio.to_thread(self.orq.responses.create, model=f"agent/{self.agent_key}", input=items, previous_response_id=self.prev)
        raise RuntimeError("tool loop did not converge")
