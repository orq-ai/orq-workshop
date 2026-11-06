"""Failure analysis starter: read the traffic traces, group them into conversations, label them.

Evaluators built before you read traces measure the failures you imagined, not the ones you
have. Run `make generate-traffic` first: this script reads those traces and labels them with the
taxonomy in classify(). The evaluators, the dataset and the experiment are the next module.

Fill in the TODOs. The script runs as is; a step with a TODO left prints what is missing.
The solution is on the `solution` branch.

    uv run python modules/failure-analysis/run.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.refund_agent.config import settings
from app.refund_agent.entities import (
    rest_post,
)

TOOL_NAMES = ("lookup_order", "get_policy", "issue_refund")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
NO_REFUND = ("refuse", "route_human", "out_of_scope")  # expected decisions where issue_refund is wrong
TRACES_URL = f"{settings.base_url}/traces"


def traffic_traces(limit: int = 100, hours: int = 2) -> list[dict[str, Any]]:
    """The last `make generate-traffic` batch as one row per router trace, oldest first.

    Same body as `orq.traces.search(from_=, to=, filters=, limit=)`, sent raw because the SDK
    model (SDK 4.17) drops the `attributes` block that holds the tool calls and the answer.
    """
    now = datetime.now(UTC)
    # TODO: add "filters": [{"field": "metadata.batch", "op": "exists"}]. The search API has no `tags` field.
    body = {"from": (now - timedelta(hours=hours)).isoformat(), "to": now.isoformat(), "limit": limit}
    if "filters" not in body:
        print("TODO     : add a metadata.batch `exists` filter to the search body, then rerun")
    response = rest_post(None, "/v3/traces/search", body)

    rows = []
    for trace in response.get("data") or []:
        attrs = trace.get("attributes") or {}
        metadata = attrs.get("metadata") or {}
        tags = json.loads((attrs.get("orq") or {}).get("tags") or "[]")  # chat-completions traces carry orq.tags
        if "traffic" not in tags and metadata.get("tag") != "traffic":  # Responses traces carry metadata.tag
            continue

        output = (attrs.get("gen_ai") or {}).get("output") or "{}"
        if isinstance(output, dict) and "_value" in output:
            # No `tools` in the request: search wraps the items as {"_value": "<json>", "type": "text"}
            output = output["_value"]
        output = json.loads(output) if isinstance(output, str) else output

        if isinstance(output, list):
            # Responses traces: a list of output items
            tool_calls = [item["name"] for item in output if item.get("type") == "function_call"]
            messages = [item for item in output if item.get("type") == "message"]
            answer = "".join(
                part.get("text", "") for message in messages for part in message.get("content") or []
            )
        else:
            # Chat completions: one assistant message
            tool_calls = [call["function"]["name"] for call in output.get("tool_calls") or []]
            answer = output.get("content") or ""

        rows.append({
            "trace_id": trace["trace_id"],
            "started_at": trace["started_at"],
            "thread_id": trace.get("thread_id") or "-",
            "batch": metadata.get("batch"),
            "variant": metadata.get("variant", "?"),
            "expected": metadata.get("expected", "?"),
            "tool_calls": tool_calls,
            "answer": answer,
        })

    newest_batch = rows[0]["batch"] if rows else None  # newest first: keep the last `make generate-traffic` only
    return sorted((row for row in rows if row["batch"] == newest_batch), key=lambda row: row["started_at"])


def conversations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the calls of one conversation by thread_id (`make generate-traffic` sets one per row).

    A conversation is 1 to 3 model calls in one thread: tool calls in order, the last call holds the answer.
    """
    grouped: list[dict[str, Any]] = []
    for row in rows:
        if grouped and grouped[-1]["thread_id"] == row["thread_id"]:
            grouped[-1]["tool_calls"] += row["tool_calls"]
            grouped[-1]["answer"] = row["answer"] or grouped[-1]["answer"]
            grouped[-1]["calls"] += 1
        else:
            grouped.append({**row, "calls": 1})
    return grouped


def classify(conv: dict[str, Any]) -> list[str]:
    """Your taxonomy. Read the conversations first, then name 2 to 4 failure modes you actually saw."""
    labels = []
    if "issue_refund" in conv["tool_calls"] and conv["expected"] in NO_REFUND:
        labels.append("refund_when_should_refuse")
    # TODO: refuses_valid_refund (expected refund, issue_refund never called)
    # TODO: answers_out_of_scope (expected out_of_scope, answer does not route to support) and is not empty
    # TODO: leaks_pii_or_tools (EMAIL.search on the answer, or tool names in a refusal)
    return labels


# ── Failure analysis by hand ────────────────────────
# Pull the traffic traces, group them into conversations by thread_id, and label each one with
# your taxonomy in classify(). Read the answers before you name a failure mode.
def step_failure_analysis() -> None:
    print("── Failure analysis by hand ────────────────────────────────────────")
    rows = traffic_traces()
    convs = conversations(rows)
    print(f"traces   : {len(rows)} traffic traces → {len(convs)} conversations (grouped by thread_id)")
    print(f"{'first trace':32} {'variant':10} {'expected':12} {'tool calls':44} labels")
    counts: Counter[str] = Counter()
    for conv in convs:
        labels = classify(conv)
        counts.update(labels)
        tool_calls = " → ".join(conv["tool_calls"]) or "-"
        print(f"{conv['trace_id']:32} {conv['variant']:10} {conv['expected']:12} {tool_calls:44} {', '.join(labels)}")
    for name, count in counts.most_common():
        print(f"failure  : {name} ({count} conversations)")
    if not set(counts) - {"refund_when_should_refuse"}:
        print("TODO     : fill in the other failure modes in classify(), then rerun")
    print(f"next     : open a flagged trace in {TRACES_URL}; read the answer before you trust the label")


if __name__ == "__main__":
    step_failure_analysis()
