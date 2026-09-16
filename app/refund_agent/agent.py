"""The local refund agent: an explicit tool-calling loop over the Responses API.

Factor 8, own your control flow: the loop below is ours, not a framework's. It is the whole
agent, and every module in the workshop runs it unchanged; what changes is the request around it
(`extra_body`, headers, the model) or the tool behind `policy_fn`.

Factor 12, stateless reducer: `run_turn` takes the full item list and returns the extended item
list. Nothing is stored server-side (`store: false`), so the caller owns the conversation and
can replay, fork or inspect it. Module 08 shows the other shape, `previous_response_id`, for
agents that live in orq.

How to use it:

    from app.refund_agent.agent import chat
    result = chat("Refund ord_a2 please, the dock does not fit my laptop.")
    result.text        # the answer
    result.tool_calls  # ["lookup_order", "get_policy", "issue_refund"]
    result.trace_id    # from the x-orq-trace-id response header; search it in the Studio

`make smoke` does exactly that once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .client import make_openai_client
from .config import DATA_DIR, settings
from .tools import RESPONSES_TOOLS, TOOL_SCHEMAS, OrderStore, dispatch, get_policy

INSTRUCTIONS = (DATA_DIR / "fixed_instructions.md").read_text()
MAX_TOOL_ROUNDS = 6  # after this many rounds of tool calls the turn gives up and hands off
HANDOFF_TEXT = "I could not complete this request. Routing you to human support."
TRACE_HEADER = "x-orq-trace-id"  # the gateway sets it on every response
IDENTITY_HEADER = "X-ORQ-IDENTITY-ID"  # who the customer is, for per-identity traces and budgets


@dataclass
class TurnResult:
    """What one turn returns: the extended item list plus what the gateway told us about it.

    `messages` starts with `{"role": "system"}`, then user and assistant messages and the tool
    items, in the order they happened. Pass it back as `history` to continue the conversation
    (module 02 does). With `api="responses"` (the default) the tool items are Responses-shaped
    (`function_call` / `function_call_output`); with `api="chat"` they are chat-shaped
    (`tool_calls` on the assistant message, `{"role": "tool"}` for results). See the table
    above `run_turn`.
    """

    messages: list[dict[str, Any]]
    trace_id: str | None = None  # from the last model call of the loop
    tool_calls: list[str] = field(default_factory=list)  # tool names, in the order called
    usage: dict[str, int] = field(default_factory=dict)  # tokens, summed over every round

    @property
    def text(self) -> str:
        """The last assistant message with content: what the customer reads."""
        for item in reversed(self.messages):
            if item.get("role") == "assistant" and item.get("content"):
                return item["content"]
        return ""


def system_message(instructions: str = INSTRUCTIONS) -> dict[str, Any]:
    """The system prompt as a message item, so a history is a plain list from index 0."""
    return {"role": "system", "content": instructions}


# The two loops below are the same algorithm on two wire formats. Item shapes, side by side:
#
#   system prompt   Responses: the `instructions=` argument, not an input item
#                   chat:      {"role": "system", "content": ...}
#   user, answer    both:      {"role": "user" | "assistant", "content": ...}
#   a tool request  Responses: {"type": "function_call", "call_id": ..., "name": ..., "arguments": ...}
#                   chat:      on the assistant message, "tool_calls": [{"id", "type": "function",
#                              "function": {"name", "arguments"}}]
#   a tool result   Responses: {"type": "function_call_output", "call_id": ..., "output": ...}
#                   chat:      {"role": "tool", "tool_call_id": ..., "content": ...}
#
# `arguments` and `output`/`content` are JSON strings on both: the model emits text, we parse it.


def run_turn(
    messages: list[dict[str, Any]],
    *,
    store: OrderStore | None = None,
    client: OpenAI | None = None,
    model: str | None = None,
    extra_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    identity: str | None = None,
    policy_fn: Callable[..., dict[str, Any]] = get_policy,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    api: str = "responses",
) -> TurnResult:
    """Run the model until it stops calling tools. Returns the extended item list.

    A leading `{"role": "system"}` message becomes the Responses `instructions`; everything else
    is sent as `input` items, in full, every round. `api="chat"` runs the same loop on
    `/chat/completions` (module 04: request-level guardrails are enforced there, not on
    Responses). `extra_body` is where the gateway controls go (fallbacks, cache, guardrails,
    identity, thread, metadata); `extra_headers` is for raw headers a module wants to add.
    """
    client = client or make_openai_client()
    store = store or OrderStore()
    model = model or settings.model
    messages = list(messages)  # a copy: the caller's history is never mutated
    if api == "chat":
        return _run_turn_chat(
            messages=messages,
            store=store,
            client=client,
            model=model,
            extra_body=extra_body,
            extra_headers=extra_headers,
            identity=identity,
            policy_fn=policy_fn,
            max_tool_rounds=max_tool_rounds,
        )

    # The Responses API takes the system prompt as `instructions`, not as an input item.
    instructions = INSTRUCTIONS
    if messages and messages[0].get("role") == "system":
        instructions = messages.pop(0)["content"]

    # Identity travels as a header. The body field `orq.identity` is not attributed in 4.14.
    identity_header = {IDENTITY_HEADER: identity} if identity else {}
    headers = {**_propagation_headers(), **identity_header, **(extra_headers or {})}

    called: list[str] = []
    usage: dict[str, int] = {}
    trace_id: str | None = None

    for _ in range(max_tool_rounds + 1):  # +1: the last round is the answer, not a tool call
        # 1. Send the full item list. Every round re-sends everything (`store=False`): the
        #    server keeps nothing, so the list in our hands is the whole conversation.
        raw = client.responses.with_raw_response.create(
            model=model,
            instructions=instructions,
            input=messages,
            tools=RESPONSES_TOOLS,
            store=False,
            extra_body=extra_body or {},
            extra_headers=headers,
        )
        trace_id = raw.headers.get(TRACE_HEADER) or trace_id
        response = raw.parse()
        if response.usage:
            usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + (response.usage.input_tokens or 0)
            usage["completion_tokens"] = usage.get("completion_tokens", 0) + (response.usage.output_tokens or 0)
            usage["total_tokens"] = usage.get("total_tokens", 0) + (response.usage.total_tokens or 0)

        # 2. Collect text and function calls from the output, appending each as an input item
        #    so the next round sees them in order. One output can hold both.
        calls = [item for item in response.output if item.type == "function_call"]
        for item in response.output:
            if item.type == "message":
                text = "".join(
                    part.text for part in item.content if getattr(part, "type", "") == "output_text"
                )
                messages.append({"role": "assistant", "content": text})
            elif item.type == "function_call":
                messages.append(
                    {
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments,
                    }
                )

        # 3. No function calls: the model answered in words. The turn is over.
        if not calls:
            break

        # 4. Run each tool and append its output under the same call_id. `dispatch` never
        #    raises: a bad call comes back as a short error the model can act on.
        for call in calls:
            arguments = json.loads(call.arguments or "{}")
            result = dispatch(store, call.name, arguments, policy_fn=policy_fn)
            called.append(call.name)
            messages.append(
                {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)}
            )
    else:
        # 5. The loop used every round without a plain answer (`for ... else` runs only when
        #    there was no `break`): give up and hand off to a human, in words the customer reads.
        messages.append({"role": "assistant", "content": HANDOFF_TEXT})

    return TurnResult(
        messages=[system_message(instructions), *messages],
        trace_id=trace_id,
        tool_calls=called,
        usage=usage,
    )


def chat(user_text: str, history: list[dict[str, Any]] | None = None, **kw: Any) -> TurnResult:
    """One customer message on top of an optional history. Adds the system prompt if missing.

    `instructions=` replaces the system prompt (the traffic generator uses it for the vulnerable
    variant); every other keyword goes to `run_turn` unchanged.
    """
    messages = list(history or [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_message(kw.pop("instructions", INSTRUCTIONS)))
    elif "instructions" in kw:
        messages[0] = system_message(kw.pop("instructions"))
    messages.append({"role": "user", "content": user_text})
    return run_turn(messages, **kw)


def _run_turn_chat(
    messages: list[dict[str, Any]],
    store: OrderStore,
    client: OpenAI,
    model: str,
    extra_body: dict[str, Any] | None,
    extra_headers: dict[str, str] | None,
    identity: str | None,
    policy_fn: Callable[..., dict[str, Any]],
    max_tool_rounds: int,
) -> TurnResult:
    """The same five-step loop over `/chat/completions`; every item stays chat-shaped.

    Module 04 needs it: request-level guardrails are enforced on chat completions, not on
    Responses. The system prompt stays in the list as `{"role": "system"}`, so the returned
    list is the input list extended, nothing prepended.
    """
    identity_header = {IDENTITY_HEADER: identity} if identity else {}
    headers = {**_propagation_headers(), **identity_header, **(extra_headers or {})}
    # GPT-5.x rejects `tools` on chat completions unless reasoning is off; a module's extra_body
    # can still override it.
    body = {"reasoning_effort": "none", **(extra_body or {})}

    called: list[str] = []
    usage: dict[str, int] = {}
    trace_id: str | None = None

    for _ in range(max_tool_rounds + 1):
        # 1. Send the full message list.
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            extra_body=body,
            extra_headers=headers,
        )
        trace_id = raw.headers.get(TRACE_HEADER) or trace_id
        completion = raw.parse()
        if completion.usage:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[key] = usage.get(key, 0) + (getattr(completion.usage, key, 0) or 0)

        # 2. Collect text and tool calls. In chat shape both sit on one assistant message.
        choice = completion.choices[0].message
        assistant: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
        if choice.tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in choice.tool_calls
            ]
        messages.append(assistant)

        # 3. No tool calls: the model answered in words.
        if not choice.tool_calls:
            break

        # 4. Run each tool; its result goes back as a `tool` message tied to the call id.
        for call in choice.tool_calls:
            arguments = json.loads(call.function.arguments or "{}")
            result = dispatch(store, call.function.name, arguments, policy_fn=policy_fn)
            called.append(call.function.name)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    else:
        # 5. Out of rounds: hand off to a human.
        messages.append({"role": "assistant", "content": HANDOFF_TEXT})

    return TurnResult(messages=messages, trace_id=trace_id, tool_calls=called, usage=usage)


def _propagation_headers() -> dict[str, str]:
    """`traceparent` for the gateway, so its spans nest under our @traced span when OTel is on.

    Empty when tracing is off, when there is no active span, or when the SDK's tracing extra
    is not installed: the call must never fail because tracing is missing.
    """
    try:
        from orq_ai_sdk.traced import propagation_headers

        return dict(propagation_headers() or {})
    except Exception:  # noqa: BLE001
        return {}
