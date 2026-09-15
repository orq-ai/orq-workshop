# %% [markdown]
# # 02 · Tracing
#
# From the zero-code traces module 01 left behind to a trace that reads `refund_turn -> tool -> llm`. Four steps: list the traces you already have, attach name, identity, thread and metadata so a conversation groups per customer, wrap the agent loop and each tool in `@traced` so one turn is one trace, then put a human annotation on the answer. Every later module (failure analysis, evals, red teaming) starts from these traces.
#
# | | |
# |---|---|
# | **Time** | 30 min |
# | **Prerequisites** | module 01 |
# | **You will have** | traces you can search by thread and customer, one trace that reads `refund_turn -> tool -> llm`, one human annotation on it |
#
# This file is both the solution script (`make m02`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.refund_agent import agent as agent_mod
from app.refund_agent import tools as tools_mod
from app.refund_agent import tracing
from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

orq = make_orq()
QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."
TRACES_URL = f"{settings.base_url}/traces"
SEARCH_WINDOW = timedelta(minutes=10)  # wide enough to catch every call of this run
MODEL_SPAN_TYPES = ("span.chat_completion", "span.responses")  # chat completions vs Responses endpoint


def spans(trace_id: str) -> list[dict[str, Any]]:
    """Span summaries of one trace, oldest first. Hides the wait: the gateway indexes a trace a few seconds after the call."""
    for _ in range(6):
        time.sleep(4)
        rows = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
        if rows:
            return sorted(rows, key=lambda span: span.get("started_at") or "")
    return []


def print_span_table(trace_id: str) -> list[dict[str, Any]]:
    """Print one row per span (root/child, type, name, status, model, id) and return the rows for later use."""
    rows = spans(trace_id)
    for span in rows:
        nesting = "root" if not span["parent_span_id"] else "  child"
        model = span.get("model") or ""
        print(f"    {nesting:7} {span['type']:22} {span['name']:28} {span['status']:5} {model:22} {span['span_id']}")
    return rows

# %% [markdown]
# ## Step 1 · The traces you already have
#
# Every gateway call is already a trace. Nothing in `app/` knows about tracing. A turn with two
# tool calls is three traces named `responses.openai`, each with cost and latency. `orq.traces.search`
# lists them; the CLI does the same with `orq traces search --from now-10m --to now -o json`.

# %%
result = chat(QUESTION)

now = datetime.now(UTC)
recent = orq.traces.search(from_=now - SEARCH_WINDOW, to=now, limit=5).model_dump(by_alias=True)

print("── Step 1 · The traces you already have ───────────────")
print(f"question : {QUESTION}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print("recent   : the last 5 traces of the workspace, one per gateway call")
for trace in recent["data"]:
    print(f"    {trace['trace_id']}  {trace['name']:16} {trace['status']:4} {trace['duration_ms']:>7.0f} ms  ${trace['cost']['total']:.6f}")
print("cli      : orq traces search --from now-10m --to now -o json | jq '.data[] | {trace_id, name}'")
print(f"next     : open {TRACES_URL}; every gateway call is its own trace, named after the endpoint")

# %% [markdown]
# ## Step 2 · Name, identity, thread, metadata
#
# Identity, thread and metadata ride on the request body as top-level fields. Two turns with the
# same thread id and the first turn's `messages` as history make one conversation; then search by
# `thread_id`. The same filters work on `identity_id`, `metadata.tier` and `name`.
#
# **Try it first:** build the `extra_body` yourself before reading the cell.

# %%
thread_id = f"ws-thread-{uuid.uuid4().hex[:8]}"
conversation_body = {
    "name": "refund-turn",
    "identity": {"id": settings.identity_id},
    "thread": {"id": thread_id},
    "metadata": {"module": "02", "tier": "free"},
}

turn_1 = chat("Can I still return ord_a3? It arrived 45 days ago.", extra_body=conversation_body)
turn_2 = chat("It was damaged in transit. Please refund it.", history=turn_1.messages, extra_body=conversation_body)

spans(turn_2.trace_id)  # only for the wait: the search below needs the last trace indexed
now = datetime.now(UTC)
thread_hits = orq.traces.search(
    from_=now - SEARCH_WINDOW,
    to=now,
    limit=10,
    filters=[{"field": "thread_id", "op": "eq", "values": [thread_id]}],  # also: identity_id, metadata.tier, name
).model_dump(by_alias=True)["data"]
turn_2_trace = orq.traces.get(trace_id=turn_2.trace_id).model_dump(by_alias=True)["trace"]

print("── Step 2 · Name, identity, thread, metadata ──────────")
print(f"thread   : {thread_id}")
print(f"turn 1   : {turn_1.trace_id}  tools {' → '.join(turn_1.tool_calls) or '(none)'}")
print(f"turn 2   : {turn_2.trace_id}  tools {' → '.join(turn_2.tool_calls) or '(none)'}")
print(f"search   : thread_id={thread_id} → {len(thread_hits)} traces: {', '.join(hit['trace_id'] for hit in thread_hits)}")
print(f"fields   : name={turn_2_trace['name']} identity_id={turn_2_trace['identity_id']} thread_id={turn_2_trace['thread_id']}")
print(f"cli      : orq traces thread {turn_2.trace_id}")
print(f"next     : in {TRACES_URL} filter on Thread ID {thread_id}; every model call of the conversation lines up")

# %% [markdown]
# One conversation, several traces: turn 1 makes one model call per tool round plus the answer,
# turn 2 usually one. In the Studio, open **Traces**, filter on Thread ID, and they line up.
#
# ## Step 3 · One trace per turn with `@traced`
#
# `TRACING=otel` in `.env`, or `tracing.setup_otel(force=True)` as here (a shell export loses to
# `.env`). Decorate the turn with `@traced(type="agent")` and each tool dispatch with
# `@traced(type="tool")`; `run_turn` already sends the `traceparent` of the active span, so the
# gateway nests its calls under ours. `app/` does not change: `agent.dispatch` is replaced at runtime.

# %%
assert tracing.setup_otel(force=True), "setup_otel() returned False"

from orq_ai_sdk.traced import traced


def traced_dispatch(store, name, arguments, policy_fn=tools_mod.get_policy):
    """The app's tool dispatch, wrapped in a tool span named after the tool."""

    @traced(type="tool", name=name)
    def call(arguments):
        return tools_mod.dispatch(store, name, arguments, policy_fn=policy_fn)

    return call(arguments)


agent_mod.dispatch = traced_dispatch  # wrap at runtime, do not edit app/


@traced(type="agent", name="refund_turn")
def refund_turn(user_text: str):
    return chat(user_text)  # run_turn adds the W3C traceparent of the active @traced span


result = refund_turn(QUESTION)
tracing.flush()  # the batch exporter ships on a timer; a short script would exit first

print("── Step 3 · One trace per turn with @traced ───────────")
print(f"question : {QUESTION}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print("spans    : oldest first")
rows = print_span_table(result.trace_id)
print(f"next     : open the trace in {TRACES_URL}; one root refund_turn, tool spans between the model calls")

# The last model span of this trace is where the annotation of step 4 goes.
model_spans = [span for span in rows if span["type"] in MODEL_SPAN_TYPES]
annotated_trace_id = result.trace_id
annotated_span_id = model_spans[-1]["span_id"] if model_spans else rows[0]["span_id"]

# %% [markdown]
# One root `refund_turn` span, one gateway call per round of the tool loop nested under it, and
# the tool spans between them in the order the model called them. `tracing.flush()` matters: the
# batch exporter ships on a timer and a short script exits first.
#
# ## Step 4 · Annotate the answer
#
# Annotations need a definition in the workspace. `rating` exists here; a missing key is a 404. If
# `rating` is missing in yours: **Optimization > Annotations > Create**, key `rating`, categorical,
# values `good` and `bad`, then rerun this cell.

# %%
print("── Step 4 · Annotate the answer ───────────────────────")
print("key      : rating=good")
print(f"span     : {annotated_span_id} of trace {annotated_trace_id}")
try:
    orq.annotations.create(
        trace_id=annotated_trace_id,
        span_id=annotated_span_id,
        annotations=[{"key": "rating", "value": "good"}],
    )
    print("verdict  : written")
    print(f"next     : open the trace in {TRACES_URL}, Annotations panel; module 17 reads these back as labels")
except Exception as exc:  # noqa: BLE001
    print(f"verdict  : failed: {str(exc)[:220]}")
    print("fix      : Studio > Optimization > Annotations > Create, key `rating`, type Categorical, values good/bad, then rerun")

# %% [markdown]
# ## Done when
#
# - One trace whose root is `refund_turn` with `lookup_order`, `get_policy`, `issue_refund` tool spans under it
# - A thread search returns every turn of one conversation
# - One `rating=good` annotation on the last model span
#
# Stretch: `uv run python modules/02-tracing/solution/stretch_langgraph.py` shows a LangGraph
# agent getting the same spans from one `setup()` call.

# %%
print(f"open {TRACES_URL} and search the trace ids above")
