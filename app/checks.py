"""make check M=<module>: verify a module's Done when list against orq.ai, one ✓ or ✗ per item.

What: each module's Done when bullets (read from its README, so the labels never drift) paired with
one predicate each that asks the API whether that state exists in the last hour.
How: `make check M=tracing`, or `uv run python -m app.checks tracing`. Exit code 1 if anything is ✗.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.refund_agent.config import ROOT

WINDOW = timedelta(minutes=60)


class TracesLike(Protocol):
    def search(self, *, from_: datetime, to: datetime, limit: int, filters: list[dict[str, Any]]) -> Any: ...
    def list_spans(self, *, trace_id: str) -> Any: ...
    def list_fields(self) -> Any: ...


class OrqLike(Protocol):
    traces: TracesLike


def _search(orq: OrqLike, filters: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    return orq.traces.search(from_=now - WINDOW, to=now, limit=limit, filters=filters).model_dump(by_alias=True)["data"]


def _named(name: str) -> list[dict[str, Any]]:
    return [{"field": "name", "op": "eq", "values": [name]}]


def _rating_field(orq: OrqLike) -> str | None:
    """The searchable field of the `rating` annotation, e.g. `annotation.<definition id>.label`."""
    fields = orq.traces.list_fields().model_dump(by_alias=True)
    stack: list[Any] = [fields]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("label") == "Annotation Rating" and str(node.get("name", "")).startswith("annotation."):
                return node["name"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _conversation_grouped(orq: OrqLike) -> bool:
    threads = Counter(t.get("thread_id") for t in _search(orq, _named("refund-turn")) if t.get("thread_id"))
    return any(count >= 2 for count in threads.values())


def _refund_turn_with_tools(orq: OrqLike) -> bool:
    for trace in _search(orq, _named("refund_turn"), limit=10):
        rows = orq.traces.list_spans(trace_id=trace["trace_id"]).model_dump(by_alias=True)["data"]
        if any(r["name"] == "refund_turn" and not r["parent_span_id"] for r in rows) and sum(r["type"] == "span.agent_tool_execution" for r in rows) >= 3:
            return True
    return False


def _langgraph_trace(orq: OrqLike) -> bool:
    return bool(_search(orq, _named("refund_langgraph"), limit=1))


def _rated_refund_turn(orq: OrqLike) -> bool:
    field = _rating_field(orq)
    if not field:
        return False
    return bool(_search(orq, _named("refund_turn") + [{"field": field, "op": "eq", "values": ["good"]}], limit=1))


Check = Callable[[OrqLike], bool]
CHECKS: dict[str, list[Check]] = {
    "tracing": [_conversation_grouped, _refund_turn_with_tools, _langgraph_trace, _rated_refund_turn],
}


def labels(slug: str) -> list[str]:
    """The module's Done when bullets, without the checkbox markup."""
    text = (ROOT / "modules" / slug / "README.md").read_text()
    block = text.split("## Done when", 1)[1].split("\n## ", 1)[0]
    return [re.sub(r"^- \[ \] ", "", line) for line in block.splitlines() if line.startswith("- [ ] ")]


def run(slug: str, orq: OrqLike) -> int:
    """Print ✓/✗ per Done when item and return the number of failures."""
    if slug not in CHECKS:
        print(f"no checks for {slug!r}; modules with checks: {', '.join(sorted(CHECKS))}")
        return 1
    names = labels(slug)
    assert len(names) == len(CHECKS[slug]), f"{slug}: {len(names)} Done when items, {len(CHECKS[slug])} checks"
    failures = 0
    for label, check in zip(names, CHECKS[slug], strict=True):
        try:
            ok = check(orq)
        except Exception as exc:  # noqa: BLE001
            ok, label = False, f"{label} (error: {str(exc)[:120]})"
        print(f"{'✓' if ok else '✗'} {label}")
        failures += not ok
    return failures


if __name__ == "__main__":
    from app.refund_agent.client import make_orq

    sys.exit(min(run(sys.argv[1] if len(sys.argv) > 1 else "", make_orq()), 1))
