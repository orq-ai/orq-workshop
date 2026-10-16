# Annotation queues and automations

!!! abstract "The human loop"
    Module 14 made the platform push numbers and events to you. This module is the human loop: a queue collects the traces worth a look, an automation fills it without you, a reviewer scores each one, and the reviewed traces become a dataset the next experiment runs on.

| | |
|---|---|
| **Time** | 25 min |
| **Prerequisites** | modules 02 and 07, `make seed` |
| **You will have** | `ws-review-queue` filled by hand and by an automation, every item annotated by API, and the bad ones promoted into `ws-review-dataset`. |

## Why

Evaluators (module 07) score at scale; humans score what evaluators cannot yet. The queue is where the two meet: an automation samples production traces into it, a reviewer says good or bad and why, and the bad ones become the rows a future experiment is measured on. Every step but one has an API; the one that does not, the automation, is a Studio form you fill once.

## The one concept to understand first

A queue item is a **span**, not a trace: `{trace_id, span_id}`. The root span (type `trace`) is what the Studio's own *Add to annotation queue* button sends. A review is one annotation on that span, with a key that exists as an annotation definition in the workspace (`rating`, `defects`); applying it marks the item reviewed. Promotion copies the message and a correction into a dataset row; the annotation stays on the trace.

```python
orq.annotation_queues.add_items(annotation_queue_id=QUEUE, items=[{"trace_id": t, "span_id": root_span}])
orq.annotations.create(trace_id=t, span_id=root_span, annotations=[{"key": "rating", "value": "bad"}, {"key": "defects", "value": ["incompleteness"]}])
orq.datasets.create_datapoint(dataset_id=DATASET, request_body=[{"inputs": {"message": user}, "expected_output": correction}])
```

![Diagram: refund-agent traces reach the annotation queue ws-review-queue through a Studio trace automation or through the add_items API; a reviewer, in the Studio or through the Annotations API, applies a rating and a defect to each queued span, which marks it reviewed; the bad ones are promoted as rows into the dataset ws-review-dataset, which module 07's experiments run on.](assets/review-loop.png)

## Steps

Open `modules/17-annotation-queues/run.py`. Every step has a `TODO`. The solution is in `solution/run.py`.

### Step 1 · Fill the queue by API

The last refund-agent traces in the project, newest first. One agent turn with tools is several traces with the same name, and only the last one ends in a message: the root span's `gen_ai.output` says which (`output_text` versus a lone `function_call`), so the hops are skipped. Run `make traffic` first so there are refund-agent traces to pick from (it names its traces `refund-traffic`, which the filter accepts next to the agent's own name); without it this step prints `traces: 0 candidates`.

```bash
$ uv run python modules/17-annotation-queues/run.py
```

```text
── Step 1 · Fill the queue by API ─────────────────────
queue    : ws-review-queue 01M52HKCW49CXPWGBG8F3FZBFH
before   : 0 items
traces   : 29 candidates, 1 are tool-loop hops without an answer
added    : 5
after    : 5 items
next     : orq annotation-queues query-items 01M52HKCW49CXPWGBG8F3FZBFH -o json | jq '.data[] | {trace_id, span_id, reviewed: (.used_human_review_ids | length > 0)}'
```

Open **Observability > Annotation queues > ws-review-queue** in the Studio: the review screen steps through the items with `J` and `K`, the interaction in the middle, the annotations panel on the right.

### Step 2 · Let an automation fill it

Automations are Studio-only: **Traces > Automations > Create**, filter `agent is ws-refund-agent` (or any trace field), sampling 100%, action *Add to annotation queue* > `ws-review-queue`. They act on future traces only. The step runs one refund turn and waits for it to appear without `add_items`:

```text
── Step 2 · Let an automation fill it ─────────────────
trace    : e39b6fdceb80d4921394679bbdabac14
verdict  : not in the queue after 30 s: no automation yet
next     : create it in the Studio (Traces > Automations, agent is ws-refund-agent, add to ws-review-queue) and run this cell again
```

That is the output before the automation exists. Create it, run the step again, and it prints `verdict  : the automation added the trace to the queue, no API call needed`. Sampling below 100% is how you keep a production queue readable; the other action, *Add to dataset*, skips the review and feeds an experiment directly.

### Step 3 · Review by API

In the Studio a reviewer clicks a value and it saves immediately. Over the API it is `annotations.create` on the item's span. The item's `used_human_review_ids` turns non-empty: that is the reviewed mark. Here a rule stands in for the human: *a customer asked about the policy and got a refusal instead of the policy* is bad, with the defect `incompleteness`. A human reviewer may disagree, which is the point of a queue. Empty answers are not rated: they are the first response of a tool loop, stopped at a `function_call` the caller never answered. Step 4 removes them from the queue together with the reviewed ones.

```text
── Step 3 · Review by API ─────────────────────────────
rated    : 4e1a4806 good  user 'One sentence: what is the refund window?'  answer 'Refunds are available within 30 days of deli'
rated    : 652602e6 good  user 'One sentence: what is the refund window?'  answer 'You may request a refund within 30 days of d'
rated    : ed36e34b bad   user 'Explain the refund policy in about 300 words.'  answer 'Refunds are generally available when you own'
rated    : d09d2836 good  user 'Explain the refund policy in about 300 words.'  answer 'For a standard refund, the order must belong'
rated    : 9e5ac3bf good  user 'One sentence: what is the refund window?'  answer 'Refunds are available within 30 days of deli'
rated    : 031b3d98 good  user 'Is a refund possible for an order delivered 40 days '  answer 'A refund after 40 days may be possible only '
reviewed : 6 now, 6 of 6 items carry a review
panel    : queue configured with annotation 01J1SHB2V08A86QB05XEV0NMFP
next     : open Observability > Annotation queues > ws-review-queue; each reviewed item shows its rating
```

One `bad` for the price of a rule, and it is probably a false positive: the rule fires on any policy question whose answer contains a refusal word ("cannot" in a list of conditions is enough), while the sibling answer to the same question in `d09d2836` was rated `good` only because it used none. A rule is a cheap first pass; the reviewer's job is exactly the row it got wrong, and the label is now on the trace either way.

The last line also configured the queue's annotations (`human_review_ids`) with the `rating` definition, so the Studio panel shows it; a queue created by API starts with none.

### Step 4 · Promote the bad ones to a dataset

The Studio's *Add to dataset* button does this per item; the API does it per span. The user message becomes `inputs.message`, the expected output is what the answer should have been. Reviewed and empty items leave the queue.

```text
── Step 4 · Promote the bad ones to a dataset ─────────
dataset  : ws-review-dataset 01M52HKCY9V0HKCDT10K20HM8B
rows     : +1 from this review, 1 total
queue    : 0 items left
cli      : orq datasets list-datapoints 01M52HKCY9V0HKCDT10K20HM8B -o json | jq -c '.data[] | {message: .inputs.message, expected_output}'
next     : point modules/07 at this dataset, or an experiment: the bad answers of today are the regression test of tomorrow
```

Point module 07's experiment at `ws-review-dataset` and the promoted row becomes a number that has to go up. Adding a trace to a dataset does not copy its annotations; the row carries the correction, the verdict stays on the trace, where the orq.ai MCP tools can still query it.

### Step 5 · The same from the CLI

```bash
$ orq annotation-queues list -o json | jq '.data[] | {_id, display_name, human_review_ids}'
$ orq annotation-queues add-items 01M52HKCW49CXPWGBG8F3FZBFH --items '[{"trace_id": "<trace>", "span_id": "<root span>"}]'
$ orq request POST /v2/traces/<trace>/spans/<span>/annotation --stdin --force <<< '{"annotations": [{"key": "rating", "value": "good"}]}'
$ orq datasets list-datapoints 01M52HKCY9V0HKCDT10K20HM8B
```

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> List the items of `ws-review-queue` with the orq.ai MCP tools. For each one without a review, read the customer message and the answer, decide `rating` good or bad against the refund policy in `app/data/kb/*.md`, add a `defects` value from the workspace's fixed list where one fits, apply the annotations with the Annotations API, and give me a table: trace id, rating, defect, one-line reason. Do not remove anything from the queue and do not touch the dataset.

The agent is a better reviewer than the rule in step 3, and slower than a human with `J`/`K`. Compare its table with your own verdicts.

## Done when

- [ ] `ws-review-queue` has items you added and, after creating the automation, one it added by itself
- [ ] Every reviewed item shows `reviewed: true` in `query-items`, and the Studio panel shows `rating`
- [ ] `ws-review-dataset` has a row for each bad answer with a correction you would defend
- [ ] You can say which findings were the agent's and which were the harness (empty answers)

## Gotchas

- Queue items are spans. `add_items` wants `{trace_id, span_id}`; `remove_items` wants span ids, not item ids.
- `retrieve_item` returns an empty model in SDK 4.16 (no `input` or `output`), and `traces.get_span` in SDK 4.14 drops `output`. Read the span over REST instead: `/v3/traces/{trace_id}/spans/{span_id}`, `attributes.gen_ai.input.messages[0].parts[0].content` for the question and `attributes.gen_ai.output` for the output items, either a JSON string or `{"_value": [...]}` for an agent whose tools run in orq. The answer is the last `message` item.
- Annotation keys must exist as definitions in the workspace; an unknown key is a 404, a `defects` value outside the fixed list (`grammatical, spelling, hallucination, repetition, inappropriate, off_topic, incompleteness, ambiguity`) is a 400. No list endpoint for definitions was found; the id of one shows up in `used_human_review_ids` after the first annotation.
- A queue created by API has no annotations configured; set `human_review_ids` (the step does) or the Studio panel is empty.
- Automations have no API and act on future traces only. Step 2 detects one by running a turn and polling for 30 seconds.
- `make reset` deletes the queue and the dataset by prefix; annotations stay on the traces.

## New in orq.ai 4.11 and 4.14

Human Review became **Annotations** with queues and an API in 4.11; 4.14 added **trace automations** with sampling and the two actions, dataset and annotation queue, and evaluator results can be corrected from the review screen.

## Go further

- Sample 10% into the queue with the automation, review for a day, and compare the bad rate with module 07's judge on the same traces: that gap is the judge's error.
- Add a `correction` annotation definition (text) and store the reviewer's rewrite on the trace itself; promote it as `expected_output` instead of the fixed sentence used here.
- Docs: [Annotation queues](https://docs.orq.ai/docs/ai-studio/observability/annotation-queues), [Annotations](https://docs.orq.ai/docs/ai-studio/observability/annotations), [Annotations API](https://docs.orq.ai/docs/ai-studio/observability/annotations-api), [Trace automations](https://docs.orq.ai/docs/ai-studio/observability/automations), [Datasets](https://docs.orq.ai/docs/ai-studio/optimize/datasets).
