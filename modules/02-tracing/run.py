"""Module 02 starter: from zero-code gateway traces to a trace that reads agent -> tool -> llm.

Factor 3: own your context window. Every turn, every tool result, is in the trace.
Factor 5: unify execution and business state. Identity, thread and metadata travel with the call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.refund_agent import agent as agent_mod
from app.refund_agent import tools as tools_mod
from app.refund_agent import tracing
from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

orq = make_orq()
QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."


def spans(trace_id: str) -> list[dict[str, Any]]:
    """Span summaries of one trace, oldest first. The gateway indexes a trace a few seconds after the call."""
    import time

    for _ in range(6):
        time.sleep(4)
        data = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
        if data:
            return sorted(data, key=lambda s: s.get("started_at") or "")
    return []


def show(trace_id: str) -> list[dict[str, Any]]:
    rows = spans(trace_id)
    for s in rows:
        parent = "root" if not s["parent_span_id"] else "  child"
        print(f"    {parent:7} {s['type']:22} {s['name']:28} {s['status']:5} {s.get('model') or '':22} {s['span_id']}")
    return rows


def step_1_zero_code() -> None:
    """Every gateway call is already a trace. Nothing in app/ knows about tracing."""
    r = chat(QUESTION)
    print(f"[1] zero-code      trace={r.trace_id} tools={r.tool_calls}")
    now = datetime.now(timezone.utc)
    res = orq.traces.search(from_=now - timedelta(minutes=10), to=now, limit=5).model_dump(by_alias=True)
    for t in res["data"]:
        print(f"    {t['trace_id']}  {t['name']:16} {t['status']:4} {t['duration_ms']:>7.0f} ms  ${t['cost']['total']:.6f}")


def step_2_thread() -> str:
    """Identity, thread and metadata ride on the request body. Two turns, one thread."""
    thread_id = f"ws-thread-{uuid.uuid4().hex[:8]}"
    # TODO: name "refund-turn", identity {"id": settings.identity_id}, thread {"id": thread_id}, metadata {"module": "02", "tier": "free"}
    body: dict[str, Any] = {}
    r1 = chat("Can I still return ord_a3? It arrived 45 days ago.", extra_body=body)
    r2 = chat("It was damaged in transit. Please refund it.", history=r1.messages, extra_body=body)
    print(f"[2] thread         id={thread_id}")
    print(f"    turn 1 trace={r1.trace_id} tools={r1.tool_calls}")
    print(f"    turn 2 trace={r2.trace_id} tools={r2.tool_calls}")
    spans(r2.trace_id)  # wait for indexing
    now = datetime.now(timezone.utc)
    # TODO: filter by thread_id (also try identity_id, metadata.tier, name)
    hits = orq.traces.search(from_=now - timedelta(minutes=10), to=now, limit=10, filters=[]).model_dump(by_alias=True)["data"]
    print(f"    search thread_id={thread_id} -> {len(hits)} traces: {[t['trace_id'] for t in hits]}")
    print(f"    render it:  orq traces thread {r2.trace_id}")
    return thread_id


def step_3_otel() -> tuple[str, str]:
    """TRACING=otel: wrap the turn and each tool with @traced. The gateway continues our trace."""
    # .env wins over the shell (load_dotenv override=True); force=True opts this step in regardless of TRACING.
    assert tracing.setup_otel(force=True), "setup_otel() returned False"

    from orq_ai_sdk.traced import traced  # noqa: F401

    def traced_dispatch(store, name, arguments, policy_fn=tools_mod.get_policy):
        # TODO: wrap the call in @traced(type="tool", name=name)
        return tools_mod.dispatch(store, name, arguments, policy_fn=policy_fn)

    agent_mod.dispatch = traced_dispatch  # wrap, do not edit app/

    # TODO: decorate with @traced(type="agent", name="refund_turn"); run_turn adds the traceparent for you
    def refund_turn(user_text: str):
        return chat(user_text)

    r = refund_turn(QUESTION)
    tracing.flush()
    print(f"[3] otel + @traced trace={r.trace_id} tools={r.tool_calls}")
    rows = show(r.trace_id)
    llm = [s for s in rows if s["type"] == "span.chat_completion"]
    return r.trace_id, (llm[-1]["span_id"] if llm else rows[0]["span_id"])


def step_4_annotation(trace_id: str, span_id: str) -> None:
    """Annotations need a definition in the workspace. A missing key is a 404."""
    try:
        # TODO: annotations=[{"key": "rating", "value": "good"}]
        orq.annotations.create(trace_id=trace_id, span_id=span_id, annotations=[])
        print(f"[4] annotation     written on span {span_id} of trace {trace_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"[4] annotation     FAILED: {str(exc)[:220]}")
        print("    Studio: Optimization > Annotations > Create, key `rating`, type Categorical, values good/bad. Then rerun.")


if __name__ == "__main__":
    step_1_zero_code()
    step_2_thread()
    trace_id, span_id = step_3_otel()
    step_4_annotation(trace_id, span_id)
    print(f"open {settings.base_url}/traces and search the trace ids above")
