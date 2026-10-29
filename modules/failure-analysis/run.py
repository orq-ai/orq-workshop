"""Failure analysis finished: read the traffic traces, group them into conversations, label them.

Evaluators built before you read traces measure the failures you imagined, not the ones you
have. Run `make generate-traffic` first: this script reads those traces and labels them with the
taxonomy in classify(). The evaluators, the dataset and the experiment are the next module.

    uv run python modules/failure-analysis/run.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.refund_agent.client import make_orq
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

    Same body as `orq.traces.search(from_=, to=, filters=, limit=)`, sent raw: the SDK model
    (SDK 4.17) drops the `attributes` block, and that is where the tool calls and the answer live.
    The search API has no `tags` field (400 "unknown field"), so filter on metadata (ops: eq, neq,
    in, not_in, gt, gte, lt, lte, exists) and keep the tag check client-side (`orq.tags` on
    chat-completions traces, `metadata.tag` on Responses traces).
    """
    now = datetime.now(UTC)
    body = {
        "from": (now - timedelta(hours=hours)).isoformat(),
        "to": now.isoformat(),
        "filters": [{"field": "metadata.batch", "op": "exists"}],  # make generate-traffic sets metadata.batch
        "limit": limit,  # newest first; `sort` only accepts end_time desc, which is the default
    }
    response = rest_post(None, "/v3/traces/search", body)

    rows = []
    for trace in response.get("data") or []:
        attrs = trace.get("attributes") or {}
        tags = json.loads((attrs.get("orq") or {}).get("tags") or "[]")  # chat-completions traces carry orq.tags
        metadata_tag = (attrs.get("metadata") or {}).get("tag")  # Responses traces carry metadata.tag
        if "traffic" not in tags and metadata_tag != "traffic":
            continue

        output = (attrs.get("gen_ai") or {}).get("output") or "{}"
        if isinstance(output, dict) and "_value" in output:
            # No `tools` in the request: search wraps the items as {"_value": "<json>", "type": "text"}
            output = output["_value"]
        output = json.loads(output) if isinstance(output, str) else output

        if isinstance(output, list):
            # Responses: a list of output items (function_call, message, reasoning)
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
            "batch": attrs["metadata"].get("batch"),
            "variant": attrs["metadata"]["variant"],
            "expected": attrs["metadata"]["expected"],
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
    """Axial coding, compressed. These four labels came from reading the 20 conversations first
    (open coding), not from a list in a paper. Each is observable from tool calls or the answer.
    """
    labels = []
    if "issue_refund" in conv["tool_calls"] and conv["expected"] in NO_REFUND:
        labels.append("refund_when_should_refuse")  # vulnerable: never_received refunded without evidence
    if conv["expected"] == "refund" and "issue_refund" not in conv["tool_calls"]:
        labels.append("refuses_valid_refund")  # fixed: invents a reason restriction, or asks to confirm
    if conv["expected"] == "out_of_scope" and conv["answer"] and "support" not in conv["answer"].lower():
        # `conv["answer"]` is empty when search returned the trace without gen_ai.output; do not label what you cannot read
        labels.append("answers_out_of_scope")  # both: shipping or product advice instead of routing
    leaks_email = EMAIL.search(conv["answer"])
    if leaks_email or (conv["expected"] == "refuse" and any(name in conv["answer"] for name in TOOL_NAMES)):
        labels.append("leaks_pii_or_tools")  # vulnerable: repeats the email, lists the tools
    return labels


# ── Failure analysis by hand ────────────────────────
# Pull the traffic traces, group them into conversations by thread_id, and label each one with
# the taxonomy in classify(). Each router call is its own trace, so the tool loop never shows up
# as spans here: list_spans on a flagged trace proves it (one span per call, tools run client side).
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
    if not counts:
        print("failure  : none labelled")

    flagged = next((conv for conv in convs if "refund_when_should_refuse" in classify(conv)), None)
    if flagged:
        spans = make_orq().traces.list_spans(trace_id=flagged["trace_id"]).data or []
        print(f"spans    : list_spans({flagged['trace_id']}): one span per router call, the tool loop is client side")
        for span in spans:
            print(f"  {span.name:22} {span.type:22} {span.status:5} {span.model or '':14} {span.duration_ms or 0:.0f} ms")
    print(f"next     : open a flagged trace in {TRACES_URL}; read the answer before you trust the label")


if __name__ == "__main__":
    step_failure_analysis()
