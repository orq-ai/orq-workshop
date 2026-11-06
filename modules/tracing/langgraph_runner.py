"""The refund agent as a LangGraph ReAct graph, traced to orq.ai over OpenTelemetry (step 4 of the tracing module).

`orq_ai_sdk.langchain.setup()` installs a global LangChain callback handler: from then on every graph
node, tool call and model call becomes a span of one trace, shipped to the same `/v2/otel` endpoint
as step 3. Call it before the LangChain classes are imported, so nothing is built without it.
Needs the optional extra: `uv sync --extra langgraph`.
"""

from __future__ import annotations

import importlib.util
import time
import warnings
from datetime import UTC, datetime, timedelta

from app.refund_agent.agent import INSTRUCTIONS
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, get_policy, issue_refund, lookup_order

RUN_NAME = "refund_langgraph"

# Fail at import, where run.py turns it into a hint, instead of halfway through run().
# The LangChain classes themselves are imported inside run(), after setup().
_missing = [name for name in ("langchain_core", "langchain_openai", "langgraph") if importlib.util.find_spec(name) is None]
if _missing:
    raise ImportError(f"missing {', '.join(_missing)}: uv sync --extra langgraph")


def run(question: str) -> str | None:
    """Run one turn through the graph and return its trace id, or None if not indexed yet."""
    warnings.filterwarnings("ignore", category=DeprecationWarning)  # create_react_agent moved in LangGraph 1.0
    from orq_ai_sdk.langchain import setup

    setup(api_key=settings.api_key, api_url=settings.base_url)

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

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

    # The model still goes through the gateway: ChatOpenAI speaks chat completions, so base_url is the router.
    # GPT-5.x rejects tools on chat completions unless reasoning_effort is "none".
    llm = ChatOpenAI(model=settings.model, api_key=settings.api_key, base_url=settings.router_url, temperature=0, reasoning_effort="none")
    graph = create_react_agent(llm, [lookup_order_tool, issue_refund_tool, get_policy_tool], prompt=INSTRUCTIONS)
    result = graph.invoke({"messages": [{"role": "user", "content": question}]}, config={"run_name": RUN_NAME})
    print(f"answer   : {result['messages'][-1].content[:100]}…")
    print(f"steps    : {' → '.join(m.type for m in result['messages'])}")

    orq = make_orq()
    for _ in range(4):
        time.sleep(5)
        now = datetime.now(UTC)
        hits = orq.traces.search(
            from_=now - timedelta(minutes=3), to=now, limit=1,
            filters=[{"field": "name", "op": "eq", "values": [RUN_NAME]}],
        ).model_dump(by_alias=True)["data"]
        if hits:
            return hits[0]["trace_id"]
    return None
