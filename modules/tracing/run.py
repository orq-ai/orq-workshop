"""The tracing module: from zero-code gateway traces to a trace that reads agent -> tool -> llm.

Factor 3: own your context window. Every turn, every tool result, is in the trace.
Factor 5: unify execution and business state. Identity, thread and metadata travel with the call.

Every step has one line marked `# CHANGE:`. The script runs as is; a step whose line is unchanged
says what to change in its output block. Run it with `uv run python modules/tracing/run.py`.
"""

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
THREAD_PREFIX = "ws-thread-"


def change_hint(text: str) -> None:
    """Say which line to change; printed only while a step still has its starter value."""
    print(f"CHANGE   : {text}")


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


def recent_traces(limit: int = 5, filters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The newest traces of the project in the search window, optionally filtered."""
    now = datetime.now(UTC)
    return orq.traces.search(from_=now - SEARCH_WINDOW, to=now, limit=limit, filters=filters or []).model_dump(by_alias=True)["data"]


# %% [markdown]
# Name the traces: `trace_name = "refund-turn"`. Watch: the newest traces are named refund-turn.

# %%
# ── Step 1 · Name the traces you already have ──
# Every gateway call is already a trace, with cost and latency, and nothing in app/ knows about
# tracing. Without a name it is called after the endpoint; with one you can find it.
def step_1_name() -> None:
    """One turn, named or not, then the last five traces of the project."""
    trace_name = "refund-turn"  # CHANGE: "refund-turn"
    result = chat(QUESTION, extra_body={"name": trace_name} if trace_name else None)
    spans(result.trace_id)  # only for the wait: the list below needs this trace indexed

    print("── Step 1 · Name the traces you already have ──────────")
    if not trace_name:
        change_hint('trace_name = None → trace_name = "refund-turn", then rerun')
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")
    print("recent   : the last 5 traces of the project, one per gateway call")
    for trace in recent_traces():
        print(f"    {trace['trace_id']}  {trace['name']:18} {trace['status']:4} {trace['duration_ms']:>7.0f} ms  ${trace['cost']['total']:.6f}")
    print("cli      : orq traces search --from now-10m --to now")
    print(f"next     : open {TRACES_URL}; with the change, the newest traces are named refund-turn")


# %% [markdown]
# Group by customer and conversation: `customer = settings.identity_id`. Watch: the thread search returns both turns.

# %%
# ── Step 2 · Group by customer and conversation ──
# Identity and thread ride on the request body as top-level fields. Two turns with the same
# thread id make one conversation; the identity says whose it is.
def step_2_conversation() -> str:
    """Two turns that carry the customer and one thread id, then a search on that thread."""
    customer = settings.identity_id  # CHANGE: settings.identity_id
    thread_id = f"{THREAD_PREFIX}{uuid.uuid4().hex[:8]}"
    body: dict[str, Any] = {}
    if customer:
        body = {"name": "refund-turn", "identity": {"id": customer}, "thread": {"id": thread_id}, "metadata": {"module": "tracing", "tier": "free"}}
    turn_1 = chat("Can I still return ord_a3? It arrived 45 days ago.", extra_body=body)
    turn_2 = chat("It was damaged in transit. Please refund it.", history=turn_1.messages, extra_body=body)
    spans(turn_2.trace_id)  # only for the wait
    hits = recent_traces(limit=10, filters=[{"field": "thread_id", "op": "eq", "values": [thread_id]}])

    print("── Step 2 · Group by customer and conversation ────────")
    if not customer:
        change_hint("customer = None → customer = settings.identity_id, then rerun")
    print(f"thread   : {thread_id}")
    print(f"turn 1   : {turn_1.trace_id}  tools {' → '.join(turn_1.tool_calls) or '(none)'}")
    print(f"turn 2   : {turn_2.trace_id}  tools {' → '.join(turn_2.tool_calls) or '(none)'}")
    print(f"search   : thread_id={thread_id} → {len(hits)} traces")
    print(f"cli      : orq traces conversation {turn_2.trace_id}")
    print(f"next     : in {TRACES_URL} filter on Thread ID {thread_id}; with the change, every model call of the conversation lines up")
    return thread_id


def traced_turn(user_text: str):
    """One refund turn under a root agent span, one tool span per tool call (orq.ai SDK @traced)."""
    from orq_ai_sdk.traced import traced

    def traced_dispatch(store, name, arguments, policy_fn=tools_mod.get_policy):
        @traced(type="tool", name=name)
        def run_tool():
            return tools_mod.dispatch(store, name, arguments, policy_fn=policy_fn)

        return run_tool()

    agent_mod.dispatch = traced_dispatch  # wrap at runtime, do not edit app/

    @traced(type="agent", name="refund_turn")
    def refund_turn(text: str):
        return chat(text)  # run_turn adds the W3C traceparent of the active @traced span

    return refund_turn(user_text)


# %% [markdown]
# Your own steps with the orq.ai SDK: `trace_my_steps = True`. Watch: a root refund_turn with tool spans nested.

# %%
# ── Step 3 · Your own steps with the orq.ai SDK ──
# The gateway sees the model calls, not your agent loop or your tools. @traced adds those steps,
# and the gateway nests its calls under them, so one turn becomes one trace.
def step_3_sdk() -> tuple[str, str]:
    """One turn, with or without your own spans. Returns the trace and its last model span."""
    trace_my_steps = True  # CHANGE: True
    if trace_my_steps:
        assert tracing.setup_otel(force=True), "setup_otel() returned False"
        result = traced_turn(QUESTION)
        tracing.flush()  # the batch exporter ships on a timer; a short script would exit first
    else:
        result = chat(QUESTION)

    print("── Step 3 · Your own steps with the orq.ai SDK ────────")
    if not trace_my_steps:
        change_hint("trace_my_steps = False → trace_my_steps = True, then rerun")
    print(f"trace    : {result.trace_id}")
    print("spans    : oldest first")
    rows = print_span_table(result.trace_id)
    print(f"next     : open the trace in {TRACES_URL}; with the change, one root refund_turn and tool spans between the model calls")

    # The last model span of this trace is where the annotation of step 5 goes.
    model_spans = [span for span in rows if span["type"] in MODEL_SPAN_TYPES]
    last_span_id = model_spans[-1]["span_id"] if model_spans else rows[0]["span_id"]
    return result.trace_id, last_span_id


# %% [markdown]
# A framework over OpenTelemetry: `otel_export = True`. Watch: one refund_langgraph trace for the whole graph.

# %%
# ── Step 4 · A framework over OpenTelemetry ──
# Already on LangGraph? Keep it. One call registers orq.ai as the OpenTelemetry destination and
# every node, tool and model call of the graph lands in one trace.
def step_4_framework() -> None:
    """The refund agent as a LangGraph graph, exported to orq.ai over OpenTelemetry."""
    otel_export = True  # CHANGE: True

    print("── Step 4 · A framework over OpenTelemetry ────────────")
    if not otel_export:
        change_hint("otel_export = False → otel_export = True, then rerun (needs: uv sync --extra langgraph)")
        return
    try:
        import langgraph_runner  # modules/tracing/langgraph_runner.py, next to this file
    except ImportError:
        change_hint("uv sync --extra langgraph, then rerun")
        return
    trace_id = langgraph_runner.run(QUESTION)
    print(f"trace    : {trace_id or 'not indexed yet, rerun in a few seconds'}")
    if trace_id:
        rows = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
        print(f"spans    : {len(rows)}, one trace for the whole graph")
    print(f"next     : open {TRACES_URL} and search refund_langgraph; the graph panel shows agent → tools → agent")


# %% [markdown]
# Annotate the answer: `rating = "good"`. Watch: the rating in the Annotations panel.

# %%
# ── Step 5 · Annotate the answer ──
# A human verdict on a span is the seed of a dataset later on. Annotations need a definition in
# the workspace: a missing key is a 404. `rating` exists after make seed-workspace.
def step_5_annotation(trace_id: str, span_id: str) -> None:
    """Put a human rating on the last model span of step 3's trace."""
    rating = "good"  # CHANGE: "good"

    print("── Step 5 · Annotate the answer ───────────────────────")
    print(f"span     : {span_id} of trace {trace_id}")
    if not rating:
        change_hint('rating = None → rating = "good", then rerun')
        return
    try:
        orq.annotations.create(trace_id=trace_id, span_id=span_id, annotations=[{"key": "rating", "value": rating}])
        print("verdict  : written")
        print(f"next     : open the trace in {TRACES_URL}, Annotations panel; the annotation-queues module reads these back as labels")
    except Exception as exc:  # noqa: BLE001
        print(f"verdict  : failed: {str(exc)[:220]}")
        print("fix      : Studio > Optimization > Annotations > Create, key `rating`, type Categorical, values good/bad, then rerun")


# %%
if __name__ == "__main__":
    step_1_name()
    step_2_conversation()
    trace_id, span_id = step_3_sdk()
    step_4_framework()
    step_5_annotation(trace_id, span_id)
    print(f"open {TRACES_URL} and search the trace ids above")
