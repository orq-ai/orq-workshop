"""Module 02 starter: from zero-code gateway traces to a trace that reads agent -> tool -> llm.

Factor 3: own your context window. Every turn, every tool result, is in the trace.
Factor 5: unify execution and business state. Identity, thread and metadata travel with the call.

Fill in the TODOs. The script runs as is; a step with an unfilled TODO says so in its output block.
Run it with `uv run python modules/02-tracing/run.py`.
"""

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


# ── Step 1 · The traces you already have ──
# Every gateway call is already a trace. Nothing in app/ knows about tracing. A turn with two tool
# calls is three traces, each with cost and latency; `orq.traces.search` lists them.
def step_1_zero_code() -> None:
    """One plain turn, then the last five traces of the workspace."""
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


# ── Step 2 · Name, identity, thread, metadata ──
# Identity, thread and metadata ride on the request body as top-level fields. Two turns with the
# same thread id and the first turn's messages as history make one conversation you can search.
def step_2_thread() -> str:
    """Two turns on one thread, then a search filtered on that thread id."""
    thread_id = f"ws-thread-{uuid.uuid4().hex[:8]}"
    # TODO: name "refund-turn", identity {"id": settings.identity_id}, thread {"id": thread_id}, metadata {"module": "02", "tier": "free"}
    conversation_body: dict[str, Any] = {}
    turn_1 = chat("Can I still return ord_a3? It arrived 45 days ago.", extra_body=conversation_body)
    turn_2 = chat("It was damaged in transit. Please refund it.", history=turn_1.messages, extra_body=conversation_body)

    spans(turn_2.trace_id)  # only for the wait: the search below needs the last trace indexed
    now = datetime.now(UTC)
    # TODO: filters=[{"field": "thread_id", "op": "eq", "values": [thread_id]}]  (also try identity_id, metadata.tier, name)
    thread_filters: list[dict[str, Any]] = []
    thread_hits = orq.traces.search(
        from_=now - SEARCH_WINDOW,
        to=now,
        limit=10,
        filters=thread_filters,
    ).model_dump(by_alias=True)["data"]

    print("── Step 2 · Name, identity, thread, metadata ──────────")
    if not conversation_body:
        print("TODO     : fill in `conversation_body` with name, identity, thread and metadata, then rerun")
    if not thread_filters:
        print("TODO     : fill in `thread_filters` so the search returns this thread only, then rerun")
    print(f"thread   : {thread_id}")
    print(f"turn 1   : {turn_1.trace_id}  tools {' → '.join(turn_1.tool_calls) or '(none)'}")
    print(f"turn 2   : {turn_2.trace_id}  tools {' → '.join(turn_2.tool_calls) or '(none)'}")
    print(f"search   : thread_id={thread_id} → {len(thread_hits)} traces: {', '.join(hit['trace_id'] for hit in thread_hits)}")
    print(f"cli      : orq traces thread {turn_2.trace_id}")
    print(f"next     : in {TRACES_URL} filter on Thread ID {thread_id}; every model call of the conversation lines up")
    return thread_id


# ── Step 3 · One trace per turn with @traced ──
# TRACING=otel: wrap the turn and each tool with @traced. run_turn sends the traceparent of the
# active span, so the gateway nests its calls under ours. app/ does not change: agent.dispatch is
# replaced at runtime.
def step_3_otel() -> tuple[str, str]:
    """One turn under a root agent span, one tool span per tool call. Returns the trace and its last model span."""
    # .env wins over the shell (load_dotenv override=True); force=True opts this step in regardless of TRACING.
    assert tracing.setup_otel(force=True), "setup_otel() returned False"

    from orq_ai_sdk.traced import traced  # noqa: F401

    def traced_dispatch(store, name, arguments, policy_fn=tools_mod.get_policy):
        """The app's tool dispatch, to be wrapped in a tool span named after the tool."""
        # TODO: wrap the call in @traced(type="tool", name=name)
        return tools_mod.dispatch(store, name, arguments, policy_fn=policy_fn)

    agent_mod.dispatch = traced_dispatch  # wrap at runtime, do not edit app/

    # TODO: decorate with @traced(type="agent", name="refund_turn"); run_turn adds the traceparent for you
    def refund_turn(user_text: str):
        return chat(user_text)

    result = refund_turn(QUESTION)
    tracing.flush()  # the batch exporter ships on a timer; a short script would exit first

    print("── Step 3 · One trace per turn with @traced ───────────")
    print(f"question : {QUESTION}")
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")
    print("spans    : oldest first")
    rows = print_span_table(result.trace_id)
    if not any(span["name"] == "refund_turn" for span in rows):
        print("TODO     : decorate refund_turn and wrap the tool dispatch with @traced, then rerun; expect a root span named refund_turn")
    print(f"next     : open the trace in {TRACES_URL}; one root refund_turn, tool spans between the model calls")

    # The last model span of this trace is where the annotation of step 4 goes.
    model_spans = [span for span in rows if span["type"] in MODEL_SPAN_TYPES]
    last_span_id = model_spans[-1]["span_id"] if model_spans else rows[0]["span_id"]
    return result.trace_id, last_span_id


# ── Step 4 · Annotate the answer ──
# Annotations need a definition in the workspace: a missing key is a 404. `rating` exists here.
def step_4_annotation(trace_id: str, span_id: str) -> None:
    """Put a human rating on the last model span of the traced turn."""
    # TODO: annotations=[{"key": "rating", "value": "good"}]
    annotations: list[dict[str, str]] = []

    print("── Step 4 · Annotate the answer ───────────────────────")
    if not annotations:
        print("TODO     : fill in `annotations` with key rating, value good, then rerun")
    print(f"span     : {span_id} of trace {trace_id}")
    try:
        orq.annotations.create(trace_id=trace_id, span_id=span_id, annotations=annotations)
        print("verdict  : written")
        print(f"next     : open the trace in {TRACES_URL}, Annotations panel; module 17 reads these back as labels")
    except Exception as exc:  # noqa: BLE001
        print(f"verdict  : failed: {str(exc)[:220]}")
        print("fix      : Studio > Optimization > Annotations > Create, key `rating`, type Categorical, values good/bad, then rerun")


if __name__ == "__main__":
    step_1_zero_code()
    step_2_thread()
    trace_id, span_id = step_3_otel()
    step_4_annotation(trace_id, span_id)
    print(f"open {TRACES_URL} and search the trace ids above")
