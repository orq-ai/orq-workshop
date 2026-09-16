# %% [markdown]
# # 02 · Tracing, stretch: let a framework do the tracing
#
# Steps 1 to 4 traced the refund agent by hand: `@traced` on the loop and on each tool, a name,
# an identity and a thread on every call. This stretch rebuilds the same agent as a LangGraph
# ReAct graph and traces it with **one line**, `orq_ai_sdk.langchain.setup()`.
#
# What you will see: the same three tools, the same instructions, the same gateway, and a trace
# with ~30 spans that the Studio renders as a graph, without a single decorator in your code.
#
# Run it with `uv run python modules/02-tracing/solution/stretch_langgraph.py`.

# %% [markdown]
# ## 1 · Register the tracer before anything else is built
#
# `setup()` installs a global LangChain callback handler. From then on every graph node, tool
# call and LLM call that LangChain runs becomes a span under one trace, shipped to the same
# `/v2/otel` endpoint module 02 used. The order matters: import and call `setup()` **before**
# the LangChain classes that will be traced, so nothing is constructed without the handler.

# %%
from __future__ import annotations

import time
import warnings
from datetime import UTC, datetime, timedelta

from app.refund_agent.agent import INSTRUCTIONS
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, get_policy, issue_refund, lookup_order

warnings.filterwarnings(
    "ignore", category=DeprecationWarning
)  # create_react_agent moved in LangGraph 1.0

from orq_ai_sdk.langchain import setup

setup(api_key=settings.api_key, api_url=settings.base_url)

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# %% [markdown]
# ## 2 · The same tools, wrapped for LangChain
#
# `@tool` turns a plain function into something the graph can call. The docstring is not a
# comment: it is the tool description the model reads when deciding what to call, so it says
# what the tool enforces. The bodies delegate to `app/refund_agent/tools.py`, the functions the
# hand-traced agent uses, so the business rules live in one place.

# %%
store = OrderStore()


@tool
def lookup_order_tool(order_id: str) -> dict:
    """Look up an order owned by the current session user."""
    return lookup_order(store, order_id)


@tool
def issue_refund_tool(order_id: str, reason: str, post_window_exception: bool = False) -> dict:
    """Issue a refund. Enforces ownership, no double refund, the EUR 500 limit and the 30-day window."""
    return issue_refund(store, order_id, reason, post_window_exception)


@tool
def get_policy_tool(topic: str) -> dict:
    """Fetch policy text. Topics: refund_basics, post_window_exceptions, abuse_patterns, shipping_and_scope."""
    return get_policy(topic)


TOOLS = [lookup_order_tool, issue_refund_tool, get_policy_tool]

# %% [markdown]
# ## 3 · The model still goes through the gateway
#
# `ChatOpenAI` speaks the OpenAI chat-completions protocol, so pointing `base_url` at the orq
# router is enough: the call is routed, budgeted and traced by the gateway like every other call
# in this workshop. `reasoning_effort="none"` is a GPT-5.x detail: on `/chat/completions` the
# model rejects tool definitions unless reasoning is off.

# %%
llm = ChatOpenAI(
    model=settings.model,
    api_key=settings.api_key,
    base_url=settings.router_url,
    temperature=0,
    reasoning_effort="none",
)

# %% [markdown]
# ## 4 · Build the graph and run one turn
#
# `create_react_agent` wires the classic loop: model → tool calls → tool results → model, until
# the model answers without calling a tool. `run_name` becomes the **trace name**, which is how
# you will find it in the Studio and with `traces.search` below. Compare with module 02, where
# the name came from `@traced(name="refund_turn")`.

# %%
QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."

graph = create_react_agent(llm, TOOLS, prompt=INSTRUCTIONS)
result = graph.invoke(
    {"messages": [{"role": "user", "content": QUESTION}]},
    config={"run_name": "refund_langgraph"},
)

# The message list is the transcript of the loop: human, then ai/tool pairs, then the final ai.
print("── Step 4 · Build the graph and run one turn ──────────")
print(f"question : {QUESTION}")
print(f"answer   : {result['messages'][-1].content[:100]}…")
print(f"steps    : {' → '.join(m.type for m in result['messages'])}")
print("next     : the trace is named refund_langgraph; step 5 searches it by that name")

# %% [markdown]
# ## 5 · Read the trace back
#
# The gateway indexes a trace a few seconds after the last span arrives. Search it by the name
# set above, then count spans by type. Each type is one LangChain concept:
#
# | span type | LangChain |
# |---|---|
# | `span.agent` | the graph and its agent nodes |
# | `span.chain` | runnables around them (prompt formatting, message handling) |
# | `span.chat_completion` | one model call, one per loop iteration |
# | `span.tool` | one tool call, so three here: lookup, policy, refund |
#
# Module 02 got the same picture with `@traced`, one span per decorated function. Here the
# framework decides the granularity, which is why the count is ~30 instead of 5.

# %%
orq = make_orq()
time.sleep(10)
now = datetime.now(UTC)
hits = orq.traces.search(
    from_=now - timedelta(minutes=3),
    to=now,
    filters=[{"field": "name", "op": "eq", "values": ["refund_langgraph"]}],
    limit=1,
).model_dump(by_alias=True)["data"]

print("── Step 5 · Read the trace back ───────────────────────")
if hits:
    trace_id = hits[0]["trace_id"]
    rows = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
    kinds: dict[str, int] = {}
    for span in rows:
        kinds[span["type"]] = kinds.get(span["type"], 0) + 1
    print(f"trace    : {trace_id}")
    print(f"spans    : {len(rows)}")
    print(f"kinds    : {', '.join(f'{kind} {count}' for kind, count in kinds.items())}")
    print(f"next     : open {settings.base_url}/traces and search the trace id; the graph panel shows agent → tools → agent")
else:
    print("trace    : not indexed yet, rerun this cell in a few seconds")

# %% [markdown]
# ## What to take away
#
# - One `setup()` call traces a whole LangGraph app; no decorators, no manual spans.
# - The trace name comes from `run_name`. Identity and thread are not set: the handler traces
#   what LangChain runs, it does not know who the customer is. That is the part module 02 did by
#   hand and the part you still own with a framework.
# - The trade-off: the framework picks the span granularity. When you need exactly one span per
#   business step, `@traced` (module 02) is the tool; when you want everything, `setup()` is.
