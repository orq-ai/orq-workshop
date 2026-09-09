"""The refund tools as an MCP server. Same functions, a different door.

Factor 4: tools are structured outputs. The MCP tool result is the same dict
`app.refund_agent.tools` returns to the local agent, so any MCP client (a coding
agent, an orq MCP Gateway, another agent) sees the same contract.

Run:   uv run python app/mcp_server.py           # http://127.0.0.1:8000/mcp
Env:   PORT (default 8000), HOST (default 127.0.0.1)
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from app.refund_agent import tools as refund_tools
from app.refund_agent.tools import OrderStore

server = MCPServer(
    name="lumen-refunds",
    instructions="Refund tools for Lumen Goods. Look up an order, read the policy, issue a refund.",
)

# One store per process. The session user is user_001, the same as the local agent.
STORE = OrderStore()


@server.tool(name="lookup_order", description=refund_tools.TOOL_SCHEMAS[0]["function"]["description"])
def lookup_order(order_id: str) -> dict:
    return refund_tools.lookup_order(STORE, order_id)


@server.tool(name="get_policy", description=refund_tools.TOOL_SCHEMAS[2]["function"]["description"])
def get_policy(topic: str) -> dict:
    return refund_tools.get_policy(topic)


@server.tool(name="issue_refund", description=refund_tools.TOOL_SCHEMAS[1]["function"]["description"])
def issue_refund(order_id: str, reason: str, post_window_exception: bool = False) -> dict:
    return refund_tools.issue_refund(STORE, order_id, reason, post_window_exception)


if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        streamable_http_path="/mcp",
    )
