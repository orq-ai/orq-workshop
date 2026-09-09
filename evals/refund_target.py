"""evaluatorq AgentTarget for the managed orq refund agent, with real tool execution.

evaluatorq's built-in orq target answers every pending function call with a synthetic
error ("Tool execution unavailable in red-teaming harness"). An agent that never sees a
real order cannot be tricked into refunding one, so a red team against it proves little.

This adapter drives the agent through the Responses API (`model="agent/<key>"`), executes
each `function_call` with app.refund_agent.tools.dispatch and continues the response with
`previous_response_id` plus a `function_call_output` item. Multi-turn attacks keep the same
response chain, so the agent sees the whole conversation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from evaluatorq.contracts import AgentTarget
from evaluatorq.redteam.contracts import (
    AgentContext,
    AgentResponse,
    Message,
    TextOutputItem,
    ToolCallOutputItem,
    ToolInfo,
)

from app.refund_agent.client import make_orq
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.tools import TOOL_SCHEMAS, OrderStore, dispatch

MAX_TOOL_ROUNDS = 6


def _get(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _text(resp: Any) -> str:
    for item in reversed(list(resp.output or [])):
        if _get(item, "type") == "message":
            parts = [_get(p, "text") or "" for p in (_get(item, "content") or []) if _get(p, "type") == "output_text"]
            if parts:
                return "".join(parts)
    return ""


class RefundAgentTarget(AgentTarget):
    """Target `agent/<key>` on orq, executing lookup_order / get_policy / issue_refund locally."""

    def __init__(self, agent_key: str, orq: Any | None = None, memory_entity_id: str | None = None) -> None:
        super().__init__(memory_entity_id)
        self.agent_key = agent_key
        self.name = agent_key
        self.orq = orq or make_orq()
        self.store = OrderStore()  # fresh orders per conversation
        self.tool_calls: list[str] = []
        self._previous_response_id: str | None = None

    def new(self) -> RefundAgentTarget:
        return type(self)(self.agent_key, self.orq)

    async def get_agent_context(self) -> AgentContext:
        variant = "vulnerable" if self.agent_key.endswith("vulnerable") else "fixed"
        instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
        tools = [
            ToolInfo(name=s["function"]["name"], description=s["function"]["description"], parameters=s["function"]["parameters"])
            for s in TOOL_SCHEMAS
        ]
        return AgentContext(
            key=self.agent_key,
            target_kind="agent",
            display_name=f"Refund agent ({variant})",
            description="Customer-service refund agent for Lumen Goods.",
            instructions=instructions,
            system_prompt=instructions,
            tools=tools,
            model=settings.model,
        )

    async def respond(self, messages: list[Message]) -> AgentResponse:
        if not messages or messages[-1].role != "user":
            raise ValueError("RefundAgentTarget forwards only the last user turn; messages[-1].role must be 'user'")
        content = messages[-1].content
        text = content if isinstance(content, str) else " ".join(_get(p, "text") or "" for p in content)
        resp = await self._create(text)
        items: list[Any] = []
        for _ in range(MAX_TOOL_ROUNDS):
            calls = [o for o in (resp.output or []) if _get(o, "type") == "function_call"]
            if not calls:
                break
            outputs = []
            for call in calls:
                name, args = _get(call, "name"), json.loads(_get(call, "arguments") or "{}")
                result = dispatch(self.store, name, args)
                self.tool_calls.append(name)
                items.append(ToolCallOutputItem(id=_get(call, "id") or "", call_id=_get(call, "call_id") or "", name=name, arguments=json.dumps(args), result=json.dumps(result)))
                outputs.append({"type": "function_call_output", "call_id": _get(call, "call_id"), "output": json.dumps(result)})
            resp = await self._create(outputs)
        items.append(TextOutputItem(text=_text(resp)))
        return AgentResponse(output=items, response_id=resp.id, model=getattr(resp, "model", None))

    async def _create(self, input: Any) -> Any:
        kwargs: dict[str, Any] = {"model": f"agent/{self.agent_key}", "input": input}
        if self._previous_response_id:
            kwargs["previous_response_id"] = self._previous_response_id
        resp = await asyncio.to_thread(self.orq.responses.create, **kwargs)
        self._previous_response_id = resp.id
        return resp
