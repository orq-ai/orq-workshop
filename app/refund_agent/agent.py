"""The local refund agent: an explicit tool-calling loop over the Responses API.

Factor 8: the loop is ours, not a framework's.
Factor 12: `run_turn` is a reducer. Items in, items out, no hidden state: the full item list is
sent on every round and nothing is stored server-side (`store: false`). Module 08 shows the other
shape, `previous_response_id`, for agents that live in orq.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .client import make_openai_client
from .config import DATA_DIR, settings
from .tools import RESPONSES_TOOLS, OrderStore, dispatch, get_policy

INSTRUCTIONS = (DATA_DIR / "fixed_instructions.md").read_text()
MAX_TOOL_ROUNDS = 6


@dataclass
class TurnResult:
    messages: list[dict[str, Any]]  # Responses input items: user/assistant messages, function_call, function_call_output
    trace_id: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        for m in reversed(self.messages):
            if m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return ""


def system_message(instructions: str = INSTRUCTIONS) -> dict[str, Any]:
    return {"role": "system", "content": instructions}


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

    A leading `{"role": "system"}` message becomes the Responses `instructions`; everything else is
    sent as `input` items, in full, every round. `api="chat"` runs the same loop on
    `/chat/completions` (module 04: request-level guardrails are enforced there, not on Responses).
    """
    client = client or make_openai_client()
    store = store or OrderStore()
    model = model or settings.model
    messages = list(messages)
    if api == "chat":
        return _run_turn_chat(messages, store, client, model, extra_body, extra_headers, identity, policy_fn, max_tool_rounds)
    instructions = INSTRUCTIONS
    if messages and messages[0].get("role") == "system":
        instructions = messages.pop(0)["content"]
    # identity travels as a header; the body field orq.identity is not attributed in 4.14
    ident = {"X-ORQ-IDENTITY-ID": identity} if identity else {}
    headers = {**_propagation_headers(), **ident, **(extra_headers or {})}
    called: list[str] = []
    usage: dict[str, int] = {}
    trace_id: str | None = None

    for _ in range(max_tool_rounds + 1):
        raw = client.responses.with_raw_response.create(
            model=model,
            instructions=instructions,
            input=messages,
            tools=RESPONSES_TOOLS,
            store=False,
            extra_body=extra_body or {},
            extra_headers=headers,
        )
        trace_id = raw.headers.get("x-orq-trace-id") or trace_id
        response = raw.parse()
        if response.usage:
            usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + (response.usage.input_tokens or 0)
            usage["completion_tokens"] = usage.get("completion_tokens", 0) + (response.usage.output_tokens or 0)
            usage["total_tokens"] = usage.get("total_tokens", 0) + (response.usage.total_tokens or 0)
        calls = [o for o in response.output if o.type == "function_call"]
        for o in response.output:
            if o.type == "message":
                text = "".join(c.text for c in o.content if getattr(c, "type", "") == "output_text")
                messages.append({"role": "assistant", "content": text})
            elif o.type == "function_call":
                messages.append({"type": "function_call", "call_id": o.call_id, "name": o.name, "arguments": o.arguments})
        if not calls:
            break
        for call in calls:
            args = json.loads(call.arguments or "{}")
            result = dispatch(store, call.name, args, policy_fn=policy_fn)
            called.append(call.name)
            messages.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
    else:
        messages.append(
            {
                "role": "assistant",
                "content": "I could not complete this request. Routing you to human support.",
            }
        )
    return TurnResult(messages=[system_message(instructions), *messages], trace_id=trace_id, tool_calls=called, usage=usage)


def chat(user_text: str, history: list[dict[str, Any]] | None = None, **kw: Any) -> TurnResult:
    """One customer message on top of an optional history. Adds the system prompt if missing."""
    messages = list(history or [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_message(kw.pop("instructions", INSTRUCTIONS)))
    elif "instructions" in kw:
        messages[0] = system_message(kw.pop("instructions"))
    messages.append({"role": "user", "content": user_text})
    return run_turn(messages, **kw)


def _run_turn_chat(messages, store, client, model, extra_body, extra_headers, identity, policy_fn, max_tool_rounds) -> TurnResult:
    """The same loop over chat completions. Messages stay chat-shaped (system/user/assistant/tool)."""
    from .tools import TOOL_SCHEMAS

    ident = {"X-ORQ-IDENTITY-ID": identity} if identity else {}
    headers = {**_propagation_headers(), **ident, **(extra_headers or {})}
    body = {"reasoning_effort": "none", **(extra_body or {})}  # GPT-5.x rejects tools on chat completions otherwise
    called: list[str] = []
    usage: dict[str, int] = {}
    trace_id: str | None = None
    for _ in range(max_tool_rounds + 1):
        raw = client.chat.completions.with_raw_response.create(model=model, messages=messages, tools=TOOL_SCHEMAS, extra_body=body, extra_headers=headers)
        trace_id = raw.headers.get("x-orq-trace-id") or trace_id
        completion = raw.parse()
        if completion.usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[k] = usage.get(k, 0) + (getattr(completion.usage, k, 0) or 0)
        choice = completion.choices[0].message
        out: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
        if choice.tool_calls:
            out["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in choice.tool_calls]
        messages.append(out)
        if not choice.tool_calls:
            break
        for call in choice.tool_calls:
            result = dispatch(store, call.function.name, json.loads(call.function.arguments or "{}"), policy_fn=policy_fn)
            called.append(call.function.name)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    else:
        messages.append({"role": "assistant", "content": "I could not complete this request. Routing you to human support."})
    return TurnResult(messages=messages, trace_id=trace_id, tool_calls=called, usage=usage)


def _propagation_headers() -> dict[str, str]:
    """traceparent for the gateway, so its spans nest under our @traced span when OTel is on."""
    try:
        from orq_ai_sdk.traced import propagation_headers

        return dict(propagation_headers() or {})
    except Exception:
        return {}
