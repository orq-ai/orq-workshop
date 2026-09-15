# %% [markdown]
# # 17 · Annotation queues and automations
#
# Module 14 made the platform push numbers and events to you. This module is the human loop: a
# queue collects the traces worth a look, an automation fills it without you, a reviewer scores
# each one, and the reviewed traces become a dataset the next experiment runs on. Four steps, all
# by API except the automation itself, which is a Studio form.
#
# | | |
# |---|---|
# | **Time** | 25 min |
# | **Prerequisites** | modules 02 and 07, `make seed` |
# | **You will have** | `ws-review-queue` filled by hand and by an automation, every item annotated by API, and the bad ones promoted into `ws-review-dataset` |
#
# This file is both the solution script (`make m17`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import ensure_annotation_queue, ensure_dataset, rest_get

orq = make_orq()
AGENT = settings.key("refund-agent")
QUEUE = ensure_annotation_queue(orq)  # ws-review-queue
DATASET = ensure_dataset(orq, "review-dataset", rows=None)  # ws-review-dataset, empty until step 4
AUTOMATION_POLLS = 6
POLL_SECONDS = 5  # 6 polls x 5 s: an automation adds the trace within about 30 s
POLICY_WORDS = ("policy", "window", "how long", "rules")
REFUSAL_WORDS = ("can't", "can’t", "cannot", "unable", "not able", "won't")  # straight and curly apostrophes
CORRECTION = (
    "Explains the 30-day window from delivery, the accepted exception reasons (damaged in transit, "
    "never received, defective on arrival) with the evidence each needs, and the EUR 500 limit."
)


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


def has_answer(trace: dict) -> bool:
    """A tool loop is several traces with the same name; only the last one ends in a message.

    `gen_ai.output` on the root span is a JSON string of output items: `output_text` means an answer,
    `function_call` alone means a hop the caller answered with a tool result. Read over REST: the
    SDK's `get_span` drops `output` in 4.14.
    """
    span = rest_get(f"/v3/traces/{trace['trace_id']}/spans/{trace['root_span_id']}").get("span", {})
    return '"output_text"' in str(
        ((span.get("attributes") or {}).get("gen_ai") or {}).get("output", "")
    )


# %% [markdown]
# ## Step 1 · Fill the queue by API
#
# A queue item is `{trace_id, span_id}`: a span, not a trace. The root span (type `trace`) is what
# the Studio's own "Add to annotation queue" button sends, so that is what we add. Source: the last
# refund-agent traces in the project, newest first, skipping what is already queued and the
# tool-loop hops that ended in a `function_call` instead of an answer.

# %%
now = datetime.now(UTC)
queued = {item["trace_id"] for item in queue_items()}
recent = orq.traces.search(
    from_=iso(now - timedelta(days=1)),
    to=iso(now),
    limit=30,
    filters=[{"field": "name", "op": "eq", "values": [AGENT]}],
).model_dump(by_alias=True)["data"]
candidates = [trace for trace in recent if trace["status"] == "ok" and trace["trace_id"] not in queued]
fresh = [trace for trace in candidates if has_answer(trace)][:5]
if fresh:
    orq.annotation_queues.add_items(
        annotation_queue_id=QUEUE,
        items=[{"trace_id": trace["trace_id"], "span_id": trace["root_span_id"]} for trace in fresh],
    )
answered = [trace for trace in candidates if has_answer(trace)]
items_now = len(queue_items())

print("── Step 1 · Fill the queue by API ─────────────────────")
print(f"queue    : ws-review-queue {QUEUE}")
print(f"before   : {len(queued)} items")
print(f"traces   : {len(candidates)} candidates, {len(candidates) - len(answered)} are tool-loop hops without an answer")
print(f"added    : {len(fresh)}")
print(f"after    : {items_now} items")
print(f"next     : orq annotation-queues query-items {QUEUE} -o json | jq '.data[] | {{trace_id, span_id, reviewed: (.used_human_review_ids | length > 0)}}'")

# %% [markdown]
# ## Step 2 · Let an automation fill it
#
# Automations are Studio-only: **Traces > Automations > Create**, filter `agent is ws-refund-agent`
# (or any trace field), sampling 100%, action *Add to annotation queue* > `ws-review-queue`. They
# act on future traces only. The cell runs one refund turn and waits: if the item appears without
# `add_items`, the automation exists; if not, this is the moment to create it and re-run the cell.

# %%
before = {item["trace_id"] for item in queue_items()}
response = orq.responses.create(
    model=f"agent/{AGENT}",
    input="Is a refund possible for an order delivered 40 days ago?",
    metadata={"ws_module": "17"},
).model_dump(by_alias=True)
trace_id = response["telemetry"]["trace_id"]

print("── Step 2 · Let an automation fill it ─────────────────")
print(f"trace    : {trace_id}")
for _ in range(AUTOMATION_POLLS):
    time.sleep(POLL_SECONDS)
    if trace_id in {item["trace_id"] for item in queue_items()}:
        print("verdict  : the automation added the trace to the queue, no API call needed")
        break
else:
    print("verdict  : not in the queue after 30 s: no automation yet")
    print(f"next     : create it in the Studio (Traces > Automations, agent is {AGENT}, add to ws-review-queue) and run this cell again")

# %% [markdown]
# ## Step 3 · Review by API
#
# In the Studio a reviewer steps through the queue with `J`/`K` and clicks a value; selecting one
# saves immediately and marks the item reviewed. The same thing over the API is one
# `annotations.create` on the item's span, with a key that exists as an annotation definition in
# the workspace (`rating`: good/bad; `defects`: a fixed multi-select). Here a rule stands in for
# the human: a customer asked about the policy and got a refusal instead of the policy. A human
# reviewer may disagree, which is the point of a queue. An empty answer is not reviewed: it is the
# first response of a tool loop, stopped at a `function_call` the caller never answered. The item's
# `used_human_review_ids` turns non-empty: that is the "reviewed" mark.

# %%
reviewed: list[tuple[str, str, str, str]] = []  # (trace_id, span_id, rating, user message)
unreviewable: list[str] = []  # span ids with no answer to judge
rating_definition: str | None = None

print("── Step 3 · Review by API ─────────────────────────────")
for item in queue_items():
    if item["used_human_review_ids"]:
        rating_definition = rating_definition or item["used_human_review_ids"][0]
        continue  # already reviewed
    span = orq.annotation_queues.retrieve_item(
        annotation_queue_id=QUEUE, item_id=item["_id"]
    ).model_dump(by_alias=True)
    user = (span.get("input") or {}).get("messages", [{}])[0].get("content", "") or ""
    answer = ((span.get("output") or {}).get("messages") or [{}])[-1].get("content", "") or ""
    if not answer.strip():
        # The agent stopped at a function_call nobody executed: nothing to review, leave it queued
        print(f"skipped  : {item['trace_id'][-8:]} empty answer (a function_call the caller never answered), user {user[:52]!r}")
        unreviewable.append(item["span_id"])
        continue
    asks_policy = any(word in user.lower() for word in POLICY_WORDS)
    refuses = any(word in answer.lower() for word in REFUSAL_WORDS)
    bad = asks_policy and refuses  # the rule: a customer asked about the policy and got a refusal instead of the policy
    rating = "bad" if bad else "good"
    annotations = [{"key": "rating", "value": rating}]
    if bad:
        annotations.append({"key": "defects", "value": ["incompleteness"]})
    orq.annotations.create(
        trace_id=item["trace_id"], span_id=item["span_id"], annotations=annotations
    )
    reviewed.append((item["trace_id"], item["span_id"], rating, user))
    print(f"rated    : {item['trace_id'][-8:]} {rating:4}  user {user[:52]!r}  answer {answer[:44]!r}")

marked = [item for item in queue_items() if item["used_human_review_ids"]]
rating_definition = rating_definition or (marked[0]["used_human_review_ids"][0] if marked else None)
if rating_definition:
    # Show `rating` in the Studio review panel; a queue created by API starts with no annotations configured
    orq.annotation_queues.update(annotation_queue_id=QUEUE, human_review_ids=[rating_definition])
items_now = len(queue_items())
print(f"reviewed : {len(reviewed)} now, {len(marked)} of {items_now} items carry a review")
print(f"panel    : queue configured with annotation {rating_definition}")
print("next     : open Observability > Annotation queues > ws-review-queue; each reviewed item shows its rating")

# %% [markdown]
# ## Step 4 · Promote the bad ones to a dataset
#
# The Studio's **Add to dataset** button does this per item; the API does it per span: the user
# message becomes `inputs.message`, and the expected output is what the answer should have been.
# Annotation values stay on the trace (they are not copied to the dataset), so the dataset row
# carries the correction, not the verdict. Reviewed items leave the queue, and so do the empty ones.

# %%
bad_rows = [
    {
        "inputs": {"message": user, "expected_decision": "answer"},
        "expected_output": CORRECTION,
    }
    for _, _, rating, user in reviewed
    if rating == "bad"
]
if bad_rows:
    orq.datasets.create_datapoint(dataset_id=DATASET, request_body=bad_rows)
if reviewed or unreviewable:
    orq.annotation_queues.remove_items(
        annotation_queue_id=QUEUE, span_ids=[span_id for _, span_id, _, _ in reviewed] + unreviewable
    )
count = len(
    orq.datasets.list_datapoints(dataset_id=DATASET, limit=100)
    .model_dump(by_alias=True)
    .get("data")
    or []
)
items_now = len(queue_items())

print("── Step 4 · Promote the bad ones to a dataset ─────────")
print(f"dataset  : ws-review-dataset {DATASET}")
print(f"rows     : +{len(bad_rows)} from this review, {count} total")
print(f"queue    : {items_now} items left")
print(f"cli      : orq datasets list-datapoints {DATASET} -o json | jq -c '.data[] | {{message: .inputs.message, expected_output}}'")
print("next     : point modules/07 at this dataset, or an experiment: the bad answers of today are the regression test of tomorrow")

# %% [markdown]
# ## Step 5 · The same from the CLI
#
# ```bash
# orq annotation-queues list -o json | jq '.data[] | {_id, display_name, human_review_ids}'
# orq annotation-queues add-items <queue_id> --items '[{"trace_id": "...", "span_id": "..."}]'
# orq request POST /v2/traces/<trace_id>/spans/<span_id>/annotation --stdin <<< '{"annotations": [{"key": "rating", "value": "good"}]}'
# orq datasets list-datapoints <dataset_id>
# ```
#
# ## What to take away
#
# - A queue item is a span, `{trace_id, span_id}`; the root span is what the Studio button adds.
# - Automations are the one Studio-only piece, and they act on future traces only.
# - A review is one `annotations.create` with a key that exists as a definition; it marks the item reviewed.
# - Promotion copies the message and a correction into a dataset; the verdict stays on the trace.

# %%
print(f"open {settings.base_url}: Observability > Annotation queues > ws-review-queue (review screen), Datasets > ws-review-dataset")
