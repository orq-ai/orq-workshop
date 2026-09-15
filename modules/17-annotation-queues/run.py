"""Module 17 starter: annotation queues and automations, the human loop.

make seed created ws-review-queue (empty) and ws-review-dataset (empty). Your job: fill the queue, let an
automation fill it, review items by API, promote the bad ones to the dataset.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import ensure_annotation_queue, ensure_dataset

orq = make_orq()
AGENT = settings.key("refund-agent")
QUEUE = ensure_annotation_queue(orq)
DATASET = ensure_dataset(orq, "review-dataset", rows=None)


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def queue_items() -> list[dict]:
    return (
        orq.annotation_queues.list_items(annotation_queue_id=QUEUE, limit=50)
        .model_dump(by_alias=True)
        .get("data")
        or []
    )


def step_1_fill() -> None:
    now = datetime.now(UTC)
    recent = orq.traces.search(
        from_=iso(now - timedelta(days=1)),
        to=iso(now),
        limit=10,
        filters=[{"field": "name", "op": "eq", "values": [AGENT]}],
    ).model_dump(by_alias=True)["data"]
    print(f"[1] {len(recent)} recent {AGENT} traces, {len(queue_items())} items in the queue")
    # TODO: for the newest 5 that are not queued yet: root span = the list_spans entry with type "trace";
    #       annotation_queues.add_items(annotation_queue_id=QUEUE, items=[{"trace_id": ..., "span_id": ...}])


def step_2_automation() -> None:
    print(
        f"[2] Studio: Traces > Automations > Create, filter agent is {AGENT}, action add to ws-review-queue; then run one turn and watch the queue"
    )
    # TODO: orq.responses.create(model=f"agent/{AGENT}", input=...), poll queue_items() for its trace_id for 30 s


def step_3_review() -> None:
    # TODO: for each unreviewed item (used_human_review_ids empty): retrieve_item -> input/output messages,
    #       decide good/bad, annotations.create(trace_id=, span_id=, annotations=[{"key": "rating", "value": ...}])
    print("[3] review: TODO")


def step_4_promote() -> None:
    # TODO: datasets.create_datapoint(dataset_id=DATASET, request_body=[{"inputs": {"message": ...}, "expected_output": ...}])
    #       for the bad ones, then annotation_queues.remove_items(annotation_queue_id=QUEUE, span_ids=[...])
    print("[4] promote: TODO")


if __name__ == "__main__":
    step_1_fill()
    step_2_automation()
    step_3_review()
    step_4_promote()
