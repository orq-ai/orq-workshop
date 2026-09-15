"""Module 17 starter: annotation queues and automations, the human loop.

Evaluators score at scale; humans score what evaluators cannot yet. A queue collects the traces
worth a look, an automation fills it without you, a reviewer scores each one, and the bad ones
become dataset rows the next experiment runs on. `make seed` created ws-review-queue (empty) and
ws-review-dataset (empty). Four steps: fill the queue by API, let an automation fill it, review
items by API, promote the bad ones to the dataset.

Fill in the TODOs. The script runs as is; a step with a TODO left prints what is missing.
The solution is in solution/run.py. Run it with `uv run python modules/17-annotation-queues/run.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import ensure_annotation_queue, ensure_dataset

orq = make_orq()
AGENT = settings.key("refund-agent")
QUEUE = ensure_annotation_queue(orq)  # ws-review-queue
DATASET = ensure_dataset(orq, "review-dataset", rows=None)  # ws-review-dataset, empty until step 4


def iso(moment: datetime) -> str:
    """The timestamp format traces.search wants: UTC, second precision, trailing Z."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def queue_items() -> list[dict]:
    """Every item in ws-review-queue as plain dicts (by_alias keeps `_id`)."""
    return (
        orq.annotation_queues.list_items(annotation_queue_id=QUEUE, limit=50)
        .model_dump(by_alias=True)
        .get("data")
        or []
    )


# ── Step 1 · Fill the queue by API ──
# A queue item is {trace_id, span_id}: a span, not a trace. The root span (type `trace`) is what
# the Studio's "Add to annotation queue" button sends, so that is what you add.
def step_1_fill() -> None:
    now = datetime.now(UTC)
    recent = orq.traces.search(
        from_=iso(now - timedelta(days=1)),
        to=iso(now),
        limit=10,
        filters=[{"field": "name", "op": "eq", "values": [AGENT]}],
    ).model_dump(by_alias=True)["data"]
    print("── Step 1 · Fill the queue by API ─────────────────────")
    print(f"queue    : ws-review-queue {QUEUE}")
    print(f"traces   : {len(recent)} recent {AGENT} traces")
    print(f"items    : {len(queue_items())} in the queue")
    # TODO: for the newest 5 that are not queued yet: root span = the list_spans entry with type "trace";
    #       annotation_queues.add_items(annotation_queue_id=QUEUE, items=[{"trace_id": ..., "span_id": ...}])
    print("TODO     : add the newest 5 unqueued traces by their root span with add_items, then rerun")


# ── Step 2 · Let an automation fill it ──
# Automations are Studio-only and act on future traces. Create one, run one agent turn, and poll
# the queue for its trace id: if it shows up without add_items, the automation works.
def step_2_automation() -> None:
    print("── Step 2 · Let an automation fill it ─────────────────")
    print(f"studio   : Traces > Automations > Create, filter agent is {AGENT}, action add to ws-review-queue")
    # TODO: orq.responses.create(model=f"agent/{AGENT}", input=...), poll queue_items() for its trace_id for 30 s
    print("TODO     : run one agent turn with responses.create and poll the queue for its trace id for 30 s, then rerun")


# ── Step 3 · Review by API ──
# A review is one annotations.create on the item's span, with a key that exists as an annotation
# definition (`rating`: good/bad). The item's used_human_review_ids turns non-empty: reviewed.
def step_3_review() -> None:
    print("── Step 3 · Review by API ─────────────────────────────")
    # TODO: for each unreviewed item (used_human_review_ids empty): retrieve_item -> input/output messages,
    #       decide good/bad, annotations.create(trace_id=, span_id=, annotations=[{"key": "rating", "value": ...}])
    print("TODO     : rate each unreviewed item with annotations.create, then rerun")


# ── Step 4 · Promote the bad ones to a dataset ──
# The user message becomes inputs.message and the expected output is what the answer should have
# been. Annotations stay on the trace; reviewed items leave the queue.
def step_4_promote() -> None:
    print("── Step 4 · Promote the bad ones to a dataset ─────────")
    # TODO: datasets.create_datapoint(dataset_id=DATASET, request_body=[{"inputs": {"message": ...}, "expected_output": ...}])
    #       for the bad ones, then annotation_queues.remove_items(annotation_queue_id=QUEUE, span_ids=[...])
    print("TODO     : write the bad ones to the dataset with create_datapoint and remove reviewed items from the queue, then rerun")


if __name__ == "__main__":
    step_1_fill()
    step_2_automation()
    step_3_review()
    step_4_promote()
