"""The three refund tools. Pure functions over an in-memory order store.

Factor 4: tools are structured outputs. The model emits JSON, this file executes it.
Factor 9: errors come back as short strings the model can act on, never stack traces.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR

WINDOW_DAYS = 30
REFUND_LIMIT_EUR = 500.0
KB_DIR = DATA_DIR / "kb"
POLICY_TOPICS = ("refund_basics", "post_window_exceptions", "abuse_patterns", "shipping_and_scope")
POST_WINDOW_REASONS = ("damaged_in_transit", "never_received", "defective_on_arrival")

_FIXTURE = json.loads((DATA_DIR / "orders.json").read_text())


class OrderStore:
    """Per-conversation mutable state. Create a fresh one per simulated customer."""

    def __init__(self, session_user_id: str | None = None) -> None:
        self.session_user_id = session_user_id or _FIXTURE["session_user_id"]
        self.orders: dict[str, dict[str, Any]] = {o["id"]: deepcopy(o) for o in _FIXTURE["orders"]}

    def owned(self, order_id: str) -> dict[str, Any] | None:
        order = self.orders.get(order_id)
        if order is None or order["owner_id"] != self.session_user_id:
            return None
        return order


def lookup_order(store: OrderStore, order_id: str) -> dict[str, Any]:
    order = store.owned(order_id)
    if order is None:
        return {"ok": False, "error": "not_found"}
    public = {k: v for k, v in order.items() if k not in ("owner_id", "notes")}
    public["within_standard_window"] = order["delivered_days_ago"] <= WINDOW_DAYS
    return {"ok": True, "order": public}


def issue_refund(
    store: OrderStore, order_id: str, reason: str, post_window_exception: bool = False
) -> dict[str, Any]:
    order = store.owned(order_id)
    if order is None:
        return {"ok": False, "error": "not_found"}
    if order["refunded"]:
        return {"ok": False, "error": "already_refunded"}
    if order["amount"] > REFUND_LIMIT_EUR:
        return {"ok": False, "error": "above_limit_needs_human_review", "limit_eur": REFUND_LIMIT_EUR}
    if order["delivered_days_ago"] > WINDOW_DAYS:
        if not post_window_exception:
            return {"ok": False, "error": "outside_window"}
        if reason not in POST_WINDOW_REASONS:
            return {"ok": False, "error": "reason_not_in_exception_list", "allowed": list(POST_WINDOW_REASONS)}
    order["refunded"] = True
    order["refund_reason"] = reason
    return {"ok": True, "order_id": order_id, "amount_refunded": order["amount"], "currency": "EUR"}


def get_policy(topic: str, kb_dir: Path = KB_DIR) -> dict[str, Any]:
    if topic not in POLICY_TOPICS:
        return {"ok": False, "error": "unknown_topic", "topics": list(POLICY_TOPICS)}
    return {"ok": True, "topic": topic, "text": (kb_dir / f"{topic}.md").read_text(), "source": "local"}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up an order owned by the current session user. Returns not_found if the order does not belong to the user.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Order id, e.g. ord_a1"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue a refund. Enforces ownership, no double refund, the EUR 500 limit and the 30-day window unless post_window_exception is true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Short reason. Outside the window must be one of damaged_in_transit, never_received, defective_on_arrival."},
                    "post_window_exception": {"type": "boolean", "default": False},
                },
                "required": ["order_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy",
            "description": "Fetch authoritative policy text. Topics: refund_basics, post_window_exceptions, abuse_patterns, shipping_and_scope.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "enum": list(POLICY_TOPICS)}},
                "required": ["topic"],
            },
        },
    },
]


def dispatch(store: OrderStore, name: str, arguments: dict[str, Any], policy_fn=get_policy) -> dict[str, Any]:
    """Route one tool call to its function. Unknown tool or bad args become a short error string."""
    try:
        if name == "lookup_order":
            return lookup_order(store, **arguments)
        if name == "issue_refund":
            return issue_refund(store, **arguments)
        if name == "get_policy":
            return policy_fn(**arguments)
        return {"ok": False, "error": f"unknown_tool:{name}"}
    except TypeError as exc:
        return {"ok": False, "error": f"bad_arguments: {exc}"}
