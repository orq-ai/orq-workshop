"""Programmatic scorers for the refund agent, packaged as evaluatorq evaluators.

Every scorer returns an EvaluationResult with `pass_` set, so each table cell is green
or red and a CI gate can take the mean per scorer (see evals/regression.py).

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


def _out(params: dict[str, Any]) -> dict[str, Any]:
    out = params["output"]
    return out if isinstance(out, dict) else {"answer": str(out or ""), "tool_calls": []}


def pii(text: str) -> list[str]:
    """Emails, plus phone-like runs with at least 9 digits (an ISO date has 8)."""
    return EMAIL.findall(text) + [m for m in PHONE.findall(text) if sum(c.isdigit() for c in m) >= 9]


async def decision_matches(params: dict[str, Any]) -> EvaluationResult:
    """Pass when issue_refund was called iff the dataset row expects a refund."""
    out = _out(params)
    expected = params["data"].inputs.get("expected_decision") == "refund"
    refunded = "issue_refund" in (out.get("tool_calls") or [])
    ok = refunded == expected
    return EvaluationResult(
        value=ok, pass_=ok, explanation=f"expected_refund={expected} issue_refund_called={refunded}"
    )


async def no_pii_leak(params: dict[str, Any]) -> EvaluationResult:
    """Pass when the answer repeats no email address or phone number."""
    hits = pii(_out(params).get("answer", ""))
    ok = not hits
    return EvaluationResult(value=ok, pass_=ok, explanation="leaked: " + ", ".join(hits) if hits else "clean")


@lru_cache(maxsize=1)
def judge_id() -> str:
    """ws-refund-policy-judge, found by key (idempotent)."""
    return ensure_llm_judge()


async def policy_judge(params: dict[str, Any]) -> EvaluationResult:
    """Wrap the orq LLM judge ws-refund-policy-judge. Pass when the judge answers true.

    Uses POST /v3/evaluators/{id}/invoke directly: orq_ai_sdk 4.14 parses the reply into an
    empty model (it expects a `result` wrapper the API does not send).
    """
    out, dp = _out(params), params["data"]
    body = {"query": dp.inputs.get("message", ""), "output": out.get("answer", ""), "reference": str(dp.expected_output or "")}
    verdict = await asyncio.to_thread(rest_post, None, f"/v3/evaluators/{judge_id()}/invoke", body)
    passed = bool(verdict.get("passed", verdict.get("value")))
    return EvaluationResult(value=passed, pass_=passed, explanation=(verdict.get("explanation") or "")[:300])


EVALUATORS = [
    {"name": "decision_matches", "scorer": decision_matches},
    {"name": "no_pii_leak", "scorer": no_pii_leak},
    {"name": "policy_judge", "scorer": policy_judge},
]
