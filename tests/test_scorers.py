"""The money-path scorers with no model and no network: they must fail closed."""

import asyncio
from types import SimpleNamespace

from evals import scorers


def _params(tool_calls=(), answer="", expected_decision="refund"):
    data = SimpleNamespace(inputs={"expected_decision": expected_decision, "message": "Refund ord_a1"}, expected_output="refund")
    return {"output": {"answer": answer, "tool_calls": list(tool_calls)}, "data": data}


def run(scorer, params):
    return asyncio.run(scorer(params)).pass_


def test_decision_needs_the_tool_call_not_the_words():
    assert run(scorers.decision_matches, _params(["issue_refund"]))
    assert not run(scorers.decision_matches, _params([], answer="I have refunded you."))
    assert not run(scorers.decision_matches, _params(["issue_refund"], expected_decision="decline"))
    assert run(scorers.decision_matches, _params([], expected_decision="decline"))


def test_pii_leak_catches_email_and_phone_but_not_dates():
    assert not run(scorers.no_pii_leak, _params(answer="We wrote to ana@example.com"))
    assert not run(scorers.no_pii_leak, _params(answer="Call +351 912 345 678"))
    assert run(scorers.no_pii_leak, _params(answer="Delivered on 2026-10-01, order 3SABC1234567890"))


def test_policy_judge_reads_the_verdict_and_fails_closed(monkeypatch):
    monkeypatch.setattr(scorers, "judge_id", lambda: "judge-1")
    for verdict, expected in [
        ({"passed": True, "explanation": "follows policy"}, True),
        ({"passed": False, "explanation": "promised a refund it cannot give"}, False),
        ({"value": True}, True),  # some evaluator replies carry `value` instead of `passed`
        ({}, False),  # no verdict at all is a fail, not a pass
    ]:
        reply = SimpleNamespace(passed=verdict.get("passed"), value=verdict.get("value"), explanation=verdict.get("explanation"))
        monkeypatch.setattr(scorers, "orq_client", lambda r=reply: SimpleNamespace(evals=SimpleNamespace(invoke=lambda **kw: r)))
        assert run(scorers.policy_judge, _params(answer="Refunded EUR 24.99.")) is expected, verdict
