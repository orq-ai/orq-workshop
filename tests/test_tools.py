"""Edge cases for the refund tools. Run: uv run pytest -q"""

from app.refund_agent.tools import OrderStore, dispatch, get_policy, issue_refund, lookup_order


def test_lookup_hides_other_users_orders():
    s = OrderStore()
    assert lookup_order(s, "ord_a1")["ok"]
    assert lookup_order(s, "ord_b1") == {"ok": False, "error": "not_found"}
    assert "notes" not in lookup_order(s, "ord_a5")["order"]


def test_in_window_refund_once():
    s = OrderStore()
    assert issue_refund(s, "ord_a1", "changed mind")["amount_refunded"] == 24.99
    assert issue_refund(s, "ord_a1", "again")["error"] == "already_refunded"


def test_window_and_exception_rules():
    s = OrderStore()
    assert issue_refund(s, "ord_a3", "changed mind")["error"] == "outside_window"
    assert issue_refund(s, "ord_a3", "goodwill", post_window_exception=True)["error"] == "reason_not_in_exception_list"
    assert issue_refund(s, "ord_a3", "damaged_in_transit", post_window_exception=True)["ok"]


def test_limit_and_unknown_tool():
    s = OrderStore()
    assert issue_refund(s, "ord_a6", "changed mind")["error"] == "above_limit_needs_human_review"
    assert dispatch(s, "nope", {})["error"] == "unknown_tool:nope"
    assert dispatch(s, "lookup_order", {"bad": 1})["error"].startswith("bad_arguments")


def test_policy_topics():
    assert get_policy("refund_basics")["ok"]
    assert get_policy("vip")["error"] == "unknown_topic"
