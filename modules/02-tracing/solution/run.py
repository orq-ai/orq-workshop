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


def spans(trace_id: str) -> list[dict[str, Any]]:
    """Span summaries of one trace, oldest first. The gateway indexes a trace a few seconds after the call."""
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

# %% [markdown]
# ## Step 1 · The traces you already have
#
# Every gateway call is already a trace. Nothing in `app/` knows about tracing. A turn with two
# tool calls is three traces named `chat.openai`, each with cost and latency. `orq.traces.search`
# lists them; the CLI does the same with `orq traces search --from now-10m --to now -o json`.

# %%
r = chat(QUESTION)
print(f"[1] zero-code      trace={r.trace_id} tools={r.tool_calls}")
now = datetime.now(UTC)
res = orq.traces.search(from_=now - timedelta(minutes=10), to=now, limit=5).model_dump(by_alias=True)
for t in res["data"]:
    print(f"    {t['trace_id']}  {t['name']:16} {t['status']:4} {t['duration_ms']:>7.0f} ms  ${t['cost']['total']:.6f}")
print("    same thing from the CLI: orq traces search --from now-10m --to now -o json | jq '.data[] | {trace_id, name}'")

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
body = {
    "name": "refund-turn",
    "identity": {"id": settings.identity_id},
    "thread": {"id": thread_id},
    "metadata": {"module": "02", "tier": "free"},
}
r1 = chat("Can I still return ord_a3? It arrived 45 days ago.", extra_body=body)
r2 = chat("It was damaged in transit. Please refund it.", history=r1.messages, extra_body=body)
print(f"[2] thread         id={thread_id}")
print(f"    turn 1 trace={r1.trace_id} tools={r1.tool_calls}")
print(f"    turn 2 trace={r2.trace_id} tools={r2.tool_calls}")
spans(r2.trace_id)  # wait for indexing
now = datetime.now(UTC)
hits = orq.traces.search(
    from_=now - timedelta(minutes=10), to=now, limit=10,
    filters=[{"field": "thread_id", "op": "eq", "values": [thread_id]}],  # also: identity_id, metadata.tier, name
).model_dump(by_alias=True)["data"]
print(f"    search thread_id={thread_id} -> {len(hits)} traces: {[t['trace_id'] for t in hits]}")
t = orq.traces.get(trace_id=r2.trace_id).model_dump(by_alias=True)["trace"]
print(f"    turn 2: name={t['name']} identity_id={t['identity_id']} thread_id={t['thread_id']}")
print(f"    render it:  orq traces thread {r2.trace_id}")

# %% [markdown]
# Four traces, one conversation: turn 1 made three model calls, turn 2 made one. In the Studio,
# open **Traces**, filter on Thread ID, and the four line up.
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
    @traced(type="tool", name=name)
    def call(arguments):
        return tools_mod.dispatch(store, name, arguments, policy_fn=policy_fn)

    return call(arguments)


agent_mod.dispatch = traced_dispatch  # wrap, do not edit app/


@traced(type="agent", name="refund_turn")
def refund_turn(user_text: str):
    return chat(user_text)  # run_turn adds the W3C traceparent of the active @traced span


r = refund_turn(QUESTION)
tracing.flush()
print(f"[3] otel + @traced trace={r.trace_id} tools={r.tool_calls}")
rows = show(r.trace_id)
llm = [s for s in rows if s["type"] in ("span.chat_completion", "span.responses")]
trace_id, span_id = r.trace_id, (llm[-1]["span_id"] if llm else rows[0]["span_id"])

# %% [markdown]
# One root `refund_turn` span, four gateway calls nested under it, three tool spans between them
# in the order the model called them. `tracing.flush()` matters: the batch exporter ships on a
# timer and a short script exits first.
#
# ## Step 4 · Annotate the answer
#
# Annotations need a definition in the workspace. `rating` exists here; a missing key is a 404. If
# `rating` is missing in yours: **Optimization > Annotations > Create**, key `rating`, categorical,
# values `good` and `bad`, then rerun this cell.

# %%
try:
    orq.annotations.create(trace_id=trace_id, span_id=span_id, annotations=[{"key": "rating", "value": "good"}])
    print(f"[4] annotation     rating=good on span {span_id} of trace {trace_id}")
except Exception as exc:  # noqa: BLE001
    print(f"[4] annotation     FAILED: {str(exc)[:220]}")
    print("    Studio: Optimization > Annotations > Create, key `rating`, type Categorical, values good/bad. Then rerun.")

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
print(f"open {settings.base_url}/traces and search the trace ids above")
