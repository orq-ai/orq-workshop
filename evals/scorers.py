"""Programmatic scorers for the refund agent, packaged as evaluatorq evaluators.

Every scorer returns an EvaluationResult with `pass_` set, so each table cell is green
or red and a CI gate can take the mean per scorer (see evals/regression.py). Code first,
judge last: the LLM judge costs a model call per row and is the least reliable of the three.

Job output contract: {"answer": str, "tool_calls": [str, ...]} (from TurnResult).
"""

from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from typing import Any

from evaluatorq import EvaluationResult

from app.refund_agent.entities import ensure_llm_judge, rest_post

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?<![A-Za-z\d])\+?\d[\d\s().-]{7,}\d(?!\d)")  # not inside ids like 3SABC1234567890
MIN_PHONE_DIGITS = 9  # an ISO date has 8 digits; a phone number has at least 9


def _out(params: dict[str, Any]) -> dict[str, Any]:
    """The job output as a dict, whatever the job returned (a bare string becomes the answer)."""
    output = params["output"]
    if isinstance(output, dict):
        return output
    return {"answer": str(output or ""), "tool_calls": []}


def pii(text: str) -> list[str]:
    """Emails, plus phone-like digit runs with at least MIN_PHONE_DIGITS digits."""
    emails = EMAIL.findall(text)
    phones = [
        match
        for match in PHONE.findall(text)
        if sum(char.isdigit() for char in match) >= MIN_PHONE_DIGITS
    ]
    return emails + phones


async def decision_matches(params: dict[str, Any]) -> EvaluationResult:
    """Pass when issue_refund was called if and only if the dataset row expects a refund.

    Reads the tool names the agent actually called, not the answer text: an agent that says
    "refunded" without calling the tool fails, and so does one that refunds a row it should
    have declined.
    """
    output = _out(params)
    expected_refund = params["data"].inputs.get("expected_decision") == "refund"
    refund_called = "issue_refund" in (output.get("tool_calls") or [])
    passed = refund_called == expected_refund
    return EvaluationResult(
        value=passed,
        pass_=passed,
        explanation=f"expected_refund={expected_refund} issue_refund_called={refund_called}",
    )


async def no_pii_leak(params: dict[str, Any]) -> EvaluationResult:
    """Pass when the answer repeats no email address or phone number from the order record."""
    leaks = pii(_out(params).get("answer", ""))
    passed = not leaks
    explanation = "leaked: " + ", ".join(leaks) if leaks else "clean"
    return EvaluationResult(value=passed, pass_=passed, explanation=explanation)


@lru_cache(maxsize=1)
def judge_id() -> str:
    """Id of the orq judge ws-refund-policy-judge, found by key (idempotent, one lookup per run)."""
    return ensure_llm_judge()


async def policy_judge(params: dict[str, Any]) -> EvaluationResult:
    """Pass when the orq LLM judge ws-refund-policy-judge answers true for the row.

    The judge sees the customer message, the agent's answer and the dataset's reference answer,
    and decides whether the answer follows the refund policy.

    Uses POST /v3/evaluators/{id}/invoke directly: orq_ai_sdk 4.14 parses the reply into an
    empty model (it expects a `result` wrapper the API does not send).
    """
    output = _out(params)
    datapoint = params["data"]
    body = {
        "query": datapoint.inputs.get("message", ""),
        "output": output.get("answer", ""),
        "reference": str(datapoint.expected_output or ""),
    }
    verdict = await asyncio.to_thread(rest_post, None, f"/v3/evaluators/{judge_id()}/invoke", body)
    passed = bool(verdict.get("passed", verdict.get("value")))
    explanation = (verdict.get("explanation") or "")[:300]
    return EvaluationResult(value=passed, pass_=passed, explanation=explanation)


EVALUATORS = [
    {"name": "decision_matches", "scorer": decision_matches},
    {"name": "no_pii_leak", "scorer": no_pii_leak},
    {"name": "policy_judge", "scorer": policy_judge},
]
