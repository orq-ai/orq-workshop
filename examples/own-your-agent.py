"""The same refund turn, three ways: your loop, a framework's loop, orq's loop.

What: one question asked three times, against the same instructions, the same three tools and the
same gateway. What changes is *who owns the agentic loop* — and what that costs you in code, in
control, and in what lands in the trace.

    1. raw orq Python SDK  `app/refund_agent/agent.py`   the loop is yours
    2. LangGraph           `create_react_agent`          the framework runs the loop
    3. managed agent       `model="agent/<key>"`         orq runs the loop, server-side

Why: teams usually already have a framework. The question is not "should we adopt orq's agent"
but "can we keep our architecture and still get prompts, routing, tracing and tool tracing from
orq". All three rows below are that answer.

How: `uv run python examples/own-your-agent.py` (needs `make seed`). LangGraph is an optional
extra: `uv sync --extra langgraph`, otherwise that leg is skipped with a note instead of failing.
"""

from __future__ import annotations

import json
import time
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any

from app.refund_agent.agent import INSTRUCTIONS, chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, dispatch

# The same sentence for every leg. Without that, the comparison is not one.
QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."
AGENT_KEY = settings.key("refund-agent")  # ws-refund-agent, created by `make seed`
GRAPH_TRACE_NAME = "own_your_agent_langgraph"  # the run name LangGraph reports, so leg 2 can find its trace
MAX_STEPS = 8
TRACE_INDEX_WAIT = 10  # the gateway indexes a trace a few seconds after the last span arrives

warnings.filterwarnings(
    "ignore", category=DeprecationWarning
)  # create_react_agent moved in LangGraph 1.0


def line(label: str, value: str) -> None:
    """One aligned fact per line, the house format the modules print."""
    print(f"{label:<9}: {value}")


# ── Leg 1 · Raw orq Python SDK · the loop is yours ──
# `chat()` is the workshop's own agent: an explicit tool-calling loop over the Responses API.
# Nothing about it is orq-specific except the base URL — the gateway is a drop-in for the OpenAI
# endpoint, which is exactly why a team can keep its own architecture and still route through orq.

print("── Leg 1 · Raw orq Python SDK ─────────────────────────")
started = time.time()
own = chat(QUESTION)
line("question", QUESTION)
line("answer", f"{own.text[:88]}…")
line("tools", " → ".join(own.tool_calls) or "(none)")
line("trace", own.trace_id or "none")
line("took", f"{time.time() - started:.1f}s")
line("next", "the loop is in app/refund_agent/agent.py — you can read all of it")

# ── Leg 2 · LangGraph · the framework runs the loop ──
# `orq_ai_sdk.langchain.setup()` installs a global LangChain callback, so every node, tool and
# model call becomes a span without touching the graph. The model speaks chat-completions here,
# not Responses, so the trace is shaped differently from leg 1 — same gateway, different endpoint.

print("── Leg 2 · LangGraph ──────────────────────────────────")
try:
    from orq_ai_sdk.langchain import setup as orq_langchain_setup

    orq_langchain_setup(api_key=settings.api_key, api_url=settings.base_url)

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    from app.refund_agent.tools import get_policy, issue_refund, lookup_order

    graph_store = OrderStore()

    @tool
    def lookup_order_tool(order_id: str) -> dict[str, Any]:
        """Look up an order owned by the current session user."""
        return lookup_order(graph_store, order_id)

    @tool
    def get_policy_tool(topic: str) -> dict[str, Any]:
        """Fetch authoritative policy text for one topic."""
        return get_policy(topic)

    @tool
    def issue_refund_tool(order_id: str, reason: str) -> dict[str, Any]:
        """Issue a refund for an order the customer owns."""
        return issue_refund(graph_store, order_id, reason)

    # `reasoning_effort="none"` is the GPT-5.x detail module 02 documents: on /chat/completions
    # the model rejects tool definitions unless reasoning is off. Leg 1 and leg 3 use the
    # Responses API, where the question does not arise — the first real difference between them.
    graph = create_react_agent(
        ChatOpenAI(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.router_url,
            temperature=0,
            reasoning_effort="none",
        ),
        [lookup_order_tool, get_policy_tool, issue_refund_tool],
        prompt=INSTRUCTIONS,
    )
    started = time.time()
    graph_result = graph.invoke(
        {"messages": [{"role": "user", "content": QUESTION}]},
        config={"run_name": GRAPH_TRACE_NAME},  # becomes the trace name, so we can find it below
    )
    steps = [m.type for m in graph_result["messages"]]
    line("question", QUESTION)
    line("answer", f"{graph_result['messages'][-1].content[:88]}…")
    line("steps", " → ".join(steps))
    line("took", f"{time.time() - started:.1f}s")

    # The callback ships spans in the background, and the gateway indexes a trace a few seconds
    # after the last one arrives. Legs 1 and 3 get a trace id back on the response itself; here
    # the run has to be named and then looked up, which is the price of not touching the graph.
    time.sleep(TRACE_INDEX_WAIT)
    now = datetime.now(UTC)
    hits = (
        make_orq()
        .traces.search(
            from_=now - timedelta(minutes=3),
            to=now,
            filters=[{"field": "name", "op": "eq", "values": [GRAPH_TRACE_NAME]}],
            limit=1,
        )
        .model_dump(by_alias=True)["data"]
    )
    line("trace", hits[0]["trace_id"] if hits else f"not indexed yet — search name={GRAPH_TRACE_NAME}")
    line("next", "one line of setup; the graph never learned it was being traced")
except ImportError:
    line("skipped", "LangGraph is an optional extra — install it with `uv sync --extra langgraph`")

# ── Leg 3 · Managed agent · orq runs the loop ──
# The agent lives in orq: instructions, model and tool schemas are configuration, not code. Your
# code posts a question and answers the `function_call` items the agent asks for. Server-side
# tools (an advisor, a knowledge base) are answered by orq and arrive already done, which is why
# a call whose `call_id` has an `orq:*` sibling must not be executed locally.

print("── Leg 3 · Managed agent ──────────────────────────────")
orq = make_orq()
agent_store = OrderStore()
started = time.time()
response = orq.responses.create(model=f"agent/{AGENT_KEY}", input=QUESTION).model_dump(by_alias=True)
traces = [response["telemetry"]["trace_id"]]
called: list[str] = []

for _ in range(MAX_STEPS):
    done_by_server = {item.get("call_id") for item in response["output"] if item["type"].startswith("orq:")}
    pending = [
        item
        for item in response["output"]
        if item["type"] == "function_call" and item["call_id"] not in done_by_server
    ]
    if not pending:
        break
    outputs = []
    for call in pending:
        called.append(call["name"])
        result = dispatch(agent_store, call["name"], json.loads(call["arguments"] or "{}"))
        outputs.append(
            {"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)}
        )
    response = orq.responses.create(
        model=f"agent/{AGENT_KEY}", previous_response_id=response["id"], input=outputs
    ).model_dump(by_alias=True)
    traces.append(response["telemetry"]["trace_id"])

answer = " ".join(
    part["text"]
    for item in response["output"]
    if item["type"] == "message"
    for part in item["content"]
    if part["type"] == "output_text"
)
line("question", QUESTION)
line("answer", f"{answer[:88]}…")
line("tools", " → ".join(called) or "(none)")
line("traces", f"{len(traces)} responses, last {traces[-1]}")
line("took", f"{time.time() - started:.1f}s")
line("next", "the instructions are in orq, not in this file — change them without a deploy")

print("── What differs ───────────────────────────────────────")
line("loop", "yours (leg 1) · the framework's (leg 2) · orq's (leg 3)")
line("tools", "your process in all three — only a managed agent can also run them server-side")
line("prompt", "a repo file in all three legs today; a Deployment would move it into orq")
line("tracing", "zero-code through the gateway · one-line callback · automatic")
line("next", "open the trace ids above side by side in https://my.orq.ai/traces")
