"""The chat's guardrail rule is created by `make seed`, and its output guardrail id is real."""

from app.refund_agent import entities


def test_seed_creates_the_chat_rule_and_the_python_guardrail_returns_its_id(monkeypatch):
    assert "chat rule" not in (entities.seed.__doc__ or "")  # the print once sat inside the docstring
    assert "ensure_chat_guardrail_rule" in entities.seed.__code__.co_names

    monkeypatch.setattr(entities, "_find_eval", lambda orq, key: None)
    monkeypatch.setattr(entities, "rest_post", lambda orq, path, body: {"id": "eval_1"})
    assert entities.ensure_python_guardrail(orq=object()) == "eval_1"  # not None: the rule's output guardrail
