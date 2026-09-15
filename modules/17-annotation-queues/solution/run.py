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


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def queue_items() -> list[dict]:
    return (
        orq.annotation_queues.list_items(annotation_queue_id=QUEUE, limit=50)
        .model_dump(by_alias=True)
        .get("data")
        or []
    )


def has_answer(trace: dict) -> bool:
    """A tool loop is several traces with the same name; only the last one ends in a message.

    `gen_ai.output` on the root span is a JSON string of output items: `output_text` means an answer,
    `function_call` alone means a hop the caller answered with a tool result. ponytail: REST, the SDK's
    `get_span` drops `output` in 4.14.
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
queued = {i["trace_id"] for i in queue_items()}
recent = orq.traces.search(
    from_=iso(now - timedelta(days=1)),
    to=iso(now),
    limit=30,
    filters=[{"field": "name", "op": "eq", "values": [AGENT]}],
).model_dump(by_alias=True)["data"]
candidates = [t for t in recent if t["status"] == "ok" and t["trace_id"] not in queued]
fresh = [t for t in candidates if has_answer(t)][:5]
if fresh:
    orq.annotation_queues.add_items(
        annotation_queue_id=QUEUE,
        items=[{"trace_id": t["trace_id"], "span_id": t["root_span_id"]} for t in fresh],
    )
print(
    f"[1] queue ws-review-queue {QUEUE}: {len(queued)} items before, {len(candidates)} candidate traces, {len(candidates) - len([t for t in candidates if has_answer(t)])} are tool-loop hops without an answer, added {len(fresh)}, {len(queue_items())} now"
)
print(
    f"    $ orq annotation-queues query-items {QUEUE} -o json | jq '.data[] | {{trace_id, span_id, reviewed: (.used_human_review_ids | length > 0)}}'"
)

# %% [markdown]
# ## Step 2 · Let an automation fill it
#
# Automations are Studio-only: **Traces > Automations > Create**, filter `agent is ws-refund-agent`
# (or any trace field), sampling 100%, action *Add to annotation queue* > `ws-review-queue`. They
# act on future traces only. The cell runs one refund turn and waits: if the item appears without
# `add_items`, the automation exists; if not, this is the moment to create it and re-run the cell.

# %%
before = {i["trace_id"] for i in queue_items()}
r = orq.responses.create(
    model=f"agent/{AGENT}",
    input="Is a refund possible for an order delivered 40 days ago?",
    metadata={"ws_module": "17"},
).model_dump(by_alias=True)
trace_id = r["telemetry"]["trace_id"]
for _ in range(6):
    time.sleep(5)
    if trace_id in {i["trace_id"] for i in queue_items()}:
        print(f"[2] automation added trace {trace_id} to the queue, no API call needed")
        break
else:
    print(
        f"[2] trace {trace_id} did not show up in 30 s: create the automation in the Studio (Traces > Automations, agent is {AGENT}, add to ws-review-queue) and run this cell again"
    )

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
for item in queue_items():
    if item["used_human_review_ids"]:
        rating_definition = rating_definition or item["used_human_review_ids"][0]
        continue  # already reviewed
    span = orq.annotation_queues.retrieve_item(
        annotation_queue_id=QUEUE, item_id=item["_id"]
    ).model_dump(by_alias=True)
    user = (span.get("input") or {}).get("messages", [{}])[0].get("content", "") or ""
    answer = ((span.get("output") or {}).get("messages") or [{}])[-1].get("content", "") or ""
    if (
        not answer.strip()
    ):  # the agent stopped at a function_call nobody executed: nothing to review, leave it queued
        print(
            f"[3] {item['trace_id'][-8:]} skipped: empty answer (a function_call the caller never answered) user={user[:52]!r}"
        )
        unreviewable.append(item["span_id"])
        continue
    asks_policy = any(w in user.lower() for w in ("policy", "window", "how long", "rules"))
    refuses = any(
        w in answer.lower() for w in ("can't", "can’t", "cannot", "unable", "not able", "won't")
    )
    bad = (
        asks_policy and refuses
    )  # the rule: a customer asked about the policy and got a refusal instead of the policy
    annotations = [{"key": "rating", "value": "bad" if bad else "good"}] + (
        [{"key": "defects", "value": ["incompleteness"]}] if bad else []
    )
    orq.annotations.create(
        trace_id=item["trace_id"], span_id=item["span_id"], annotations=annotations
    )
    reviewed.append((item["trace_id"], item["span_id"], "bad" if bad else "good", user))
    print(
        f"[3] {item['trace_id'][-8:]} rating={'bad ' if bad else 'good'} user={user[:52]!r} answer={answer[:44]!r}"
    )
marked = [i for i in queue_items() if i["used_human_review_ids"]]
rating_definition = rating_definition or (marked[0]["used_human_review_ids"][0] if marked else None)
if rating_definition:
    orq.annotation_queues.update(
        annotation_queue_id=QUEUE, human_review_ids=[rating_definition]
    )  # the Studio panel now shows `rating`
print(
    f"    reviewed {len(reviewed)} now, {len(marked)} of {len(queue_items())} items carry a review; queue configured with annotation {rating_definition}"
)

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
        "expected_output": "Explains the 30-day window from delivery, the accepted exception reasons (damaged in transit, never received, defective on arrival) with the evidence each needs, and the EUR 500 limit.",
    }
    for _, _, rating, user in reviewed
    if rating == "bad"
]
if bad_rows:
    orq.datasets.create_datapoint(dataset_id=DATASET, request_body=bad_rows)
if reviewed or unreviewable:
    orq.annotation_queues.remove_items(
        annotation_queue_id=QUEUE, span_ids=[span for _, span, _, _ in reviewed] + unreviewable
    )
count = len(
    orq.datasets.list_datapoints(dataset_id=DATASET, limit=100)
    .model_dump(by_alias=True)
    .get("data")
    or []
)
print(
    f"[4] dataset ws-review-dataset {DATASET}: +{len(bad_rows)} rows from this review, {count} total; queue now {len(queue_items())} items"
)
print(
    f"    $ orq datasets list-datapoints {DATASET} -o json | jq -c '.data[] | {{message: .inputs.message, expected_output}}'"
)
print(
    "    next: point modules/07 at this dataset, or an experiment: the bad answers of today are the regression test of tomorrow"
)

# %% [markdown]
# ## Step 5 · The same from the CLI
#
# ```bash
# orq annotation-queues list -o json | jq '.data[] | {_id, display_name, human_review_ids}'
# orq annotation-queues add-items <queue_id> --items '[{"trace_id": "...", "span_id": "..."}]'
# orq request POST /v2/traces/<trace_id>/spans/<span_id>/annotation --stdin <<< '{"annotations": [{"key": "rating", "value": "good"}]}'
# orq datasets list-datapoints <dataset_id>
# ```

# %%
print(
    f"open {settings.base_url}: Observability > Annotation queues > ws-review-queue (review screen), Datasets > ws-review-dataset"
)
