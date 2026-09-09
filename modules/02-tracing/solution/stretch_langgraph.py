"""Stretch: the same refund agent as a LangGraph ReAct graph, traced with one `setup()` call.

`orq_ai_sdk.langchain.setup` registers a global callback: every node, tool and LLM call becomes a span
under one trace, and the Studio renders the graph next to it. The LLM still goes through the gateway.
"""

from __future__ import annotations

import time
import warnings
from datetime import datetime, timedelta, timezone

from app.refund_agent.agent import INSTRUCTIONS
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, get_policy, issue_refund, lookup_order

warnings.filterwarnings("ignore", category=DeprecationWarning)  # create_react_agent moved in LangGraph 1.0

from orq_ai_sdk.langchain import setup  # noqa: E402

setup(api_key=settings.api_key, api_url=settings.base_url)  # before any graph or model is built

from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402

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


if __name__ == "__main__":
    llm = ChatOpenAI(model=settings.model, api_key=settings.api_key, base_url=settings.router_url, temperature=0)
    graph = create_react_agent(llm, [lookup_order_tool, issue_refund_tool, get_policy_tool], prompt=INSTRUCTIONS)
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Refund ord_a2 please, the dock does not fit my laptop."}]},
        config={"run_name": "refund_langgraph"},
    )
    print("answer :", result["messages"][-1].content[:120])
    print("steps  :", [m.type for m in result["messages"]])

    orq = make_orq()
    time.sleep(10)
    now = datetime.now(timezone.utc)
    hits = orq.traces.search(from_=now - timedelta(minutes=3), to=now, filters=[{"field": "name", "op": "eq", "values": ["refund_langgraph"]}], limit=1).model_dump(by_alias=True)["data"]
    if hits:
        tid = hits[0]["trace_id"]
        rows = orq.traces.list_spans(trace_id=tid).model_dump(by_alias=True)["data"]
        kinds = {}
        for s in rows:
            kinds[s["type"]] = kinds.get(s["type"], 0) + 1
        print(f"trace  : {tid}  spans={len(rows)}  {kinds}")
        print("open   :", f"{settings.base_url}/traces and search the trace id; the graph panel shows agent -> tools -> agent")
