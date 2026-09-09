"""The local refund agent: an explicit tool-calling loop over chat.completions.

Factor 8: the loop is ours, not a framework's.
Factor 12: `run_turn` is a reducer. Messages in, messages out, no hidden state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import OpenAI

from .client import make_openai_client
from .config import DATA_DIR, settings
from .tools import TOOL_SCHEMAS, OrderStore, dispatch, get_policy

INSTRUCTIONS = (DATA_DIR / "fixed_instructions.md").read_text()
MAX_TOOL_ROUNDS = 6


@dataclass
class TurnResult:
    messages: list[dict[str, Any]]
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
) -> TurnResult:
    """Run the model until it stops calling tools. Returns the extended message list."""
    client = client or make_openai_client()
    store = store or OrderStore()
    model = model or settings.model
    messages = list(messages)
    # identity travels as a header; the body field orq.identity is not attributed in 4.14
    ident = {"X-ORQ-IDENTITY-ID": identity} if identity else {}
    headers = {**_propagation_headers(), **ident, **(extra_headers or {})}
    called: list[str] = []
    usage: dict[str, int] = {}
    trace_id: str | None = None

    for _ in range(max_tool_rounds + 1):
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            extra_body=extra_body or {},
            extra_headers=headers,
        )
        trace_id = raw.headers.get("x-orq-trace-id") or trace_id
        completion = raw.parse()
        if completion.usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[k] = usage.get(k, 0) + (getattr(completion.usage, k, 0) or 0)
        choice = completion.choices[0].message
        messages.append(_assistant_message(choice))
        if not choice.tool_calls:
            break
        for call in choice.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = dispatch(store, call.function.name, args, policy_fn=policy_fn)
            called.append(call.function.name)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    else:
        messages.append({"role": "assistant", "content": "I could not complete this request. Routing you to human support."})
    return TurnResult(messages=messages, trace_id=trace_id, tool_calls=called, usage=usage)


def chat(user_text: str, history: list[dict[str, Any]] | None = None, **kw: Any) -> TurnResult:
    """One customer message on top of an optional history. Adds the system prompt if missing."""
    messages = list(history or [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_message(kw.pop("instructions", INSTRUCTIONS)))
    messages.append({"role": "user", "content": user_text})
    return run_turn(messages, **kw)


def _propagation_headers() -> dict[str, str]:
    """traceparent for the gateway, so its spans nest under our @traced span when OTel is on."""
    try:
        from orq_ai_sdk.traced import propagation_headers

        return dict(propagation_headers() or {})
    except Exception:
        return {}


def _assistant_message(msg: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls
        ]
    return out
