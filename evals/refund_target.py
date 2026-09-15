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

MAX_TOOL_ROUNDS = 6  # an attack that keeps the agent calling tools forever must still end


def _get(item: Any, key: str) -> Any:
    """Read a field from a Responses API item, whether the SDK gave us a dict or a model."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _text(response: Any) -> str:
    """The text of the last `message` item in a response, or "" when the model only called tools."""
    for item in reversed(list(response.output or [])):
        if _get(item, "type") != "message":
            continue
        parts = [
            _get(part, "text") or ""
            for part in (_get(item, "content") or [])
            if _get(part, "type") == "output_text"
        ]
        if parts:
            return "".join(parts)
    return ""


class RefundAgentTarget(AgentTarget):
    """Target `agent/<key>` on orq, executing lookup_order / get_policy / issue_refund locally.

    One instance is one conversation: a fresh OrderStore, an empty tool-call log and its own
    `previous_response_id` chain. evaluatorq calls `new()` per attack to get a clean one.
    """

    def __init__(self, agent_key: str, orq: Any | None = None, memory_entity_id: str | None = None) -> None:
        super().__init__(memory_entity_id)
        self.agent_key = agent_key
        self.name = agent_key
        self.orq = orq or make_orq()
        self.store = OrderStore()  # fresh orders per conversation
        self.tool_calls: list[str] = []
        self._previous_response_id: str | None = None

    def new(self) -> RefundAgentTarget:
        """A clean conversation against the same agent, sharing the orq client."""
        return type(self)(self.agent_key, self.orq)

    async def get_agent_context(self) -> AgentContext:
        """What the judge knows about the target: instructions, tools, model, and which variant it is."""
        variant = "vulnerable" if self.agent_key.endswith("vulnerable") else "fixed"
        instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
        tools = [
            ToolInfo(
                name=schema["function"]["name"],
                description=schema["function"]["description"],
                parameters=schema["function"]["parameters"],
            )
            for schema in TOOL_SCHEMAS
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
        """Send the last user turn to the agent, run its tool loop, return text plus every tool call.

        Only the last message is forwarded: earlier turns are already in the response chain on
        the orq side (`previous_response_id`), so resending them would duplicate the history.
        """
        if not messages or messages[-1].role != "user":
            raise ValueError("RefundAgentTarget forwards only the last user turn; messages[-1].role must be 'user'")
        content = messages[-1].content
        if isinstance(content, str):
            text = content
        else:
            text = " ".join(_get(part, "text") or "" for part in content)
        response = await self._create(text)

        items: list[Any] = []
        for _ in range(MAX_TOOL_ROUNDS):
            calls = [item for item in (response.output or []) if _get(item, "type") == "function_call"]
            if not calls:
                break
            outputs = []
            for call in calls:
                name = _get(call, "name")
                args = json.loads(_get(call, "arguments") or "{}")
                result = dispatch(self.store, name, args)
                self.tool_calls.append(name)
                # The judge sees the tool call and its result as output items, so "did the agent
                # actually issue a refund?" is answered from the record, not from the answer text.
                items.append(
                    ToolCallOutputItem(
                        id=_get(call, "id") or "",
                        call_id=_get(call, "call_id") or "",
                        name=name,
                        arguments=json.dumps(args),
                        result=json.dumps(result),
                    )
                )
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": _get(call, "call_id"),
                        "output": json.dumps(result),
                    }
                )
            response = await self._create(outputs)
        items.append(TextOutputItem(text=_text(response)))
        return AgentResponse(output=items, response_id=response.id, model=getattr(response, "model", None))

    async def _create(self, input: Any) -> Any:
        """One `responses.create` against `agent/<key>`, continuing the conversation's response chain."""
        kwargs: dict[str, Any] = {"model": f"agent/{self.agent_key}", "input": input}
        if self._previous_response_id:
            kwargs["previous_response_id"] = self._previous_response_id
        response = await asyncio.to_thread(self.orq.responses.create, **kwargs)
        self._previous_response_id = response.id
        return response
