"""Module 10 starter: the refund tools behind an orq MCP Gateway.

Fill the TODOs. The solution is in solution/run.py. Start the local server first:
    make mcp-server            # app/mcp_server.py on http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import asyncio
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

LOCAL_URL = "http://127.0.0.1:8000/mcp"
PUBLIC_FALLBACK_URL = "https://mcp.deepwiki.com/mcp"  # public, no auth; stand-in while MCP_SERVER_URL is empty

orq = make_orq()
SERVER_KEY = settings.key("refund-mcp")
GATEWAY_KEY = settings.key("refund-gateway")


def rest_id(kind: str, key: str) -> str | None:
    """MCP Portal records carry `_id`; the SDK models drop it. Read it raw."""
    r = httpx.get(f"{settings.base_url}/v2/{kind}", params={"limit": 100}, headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30)
    return next((d.get("_id") for d in r.json().get("data", []) if d.get("key") == key), None)


async def list_tools(url: str, headers: dict[str, str] | None = None) -> list[str]:
    client = create_mcp_http_client(headers=headers) if headers else None
    async with streamable_http_client(url, http_client=client) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            # TODO: call lookup_order with {"order_id": "ord_a2"} via session.call_tool and print the result
            return [t.name for t in tools.tools]


def step_1_local_server() -> None:
    print("[1] local MCP server", LOCAL_URL)
    try:
        print("   ", asyncio.run(list_tools(LOCAL_URL)))
    except Exception as exc:
        print(f"    not reachable ({type(exc).__name__}); run `make mcp-server` in another terminal")


def step_2_register_server() -> str | None:
    upstream = settings.mcp_server_url or PUBLIC_FALLBACK_URL
    print(f"[2] MCP Portal server {SERVER_KEY} -> {upstream}")
    server_id = rest_id("mcp-servers", SERVER_KEY)
    if server_id is None:
        # TODO: orq.mcp_servers.create(key=SERVER_KEY, display_name=..., connection={"type": "MCP_CONNECTION_TYPE_HTTP", "url": upstream},
        #       auth={"type": "MCP_AUTH_TYPE_NONE"}, default_tool_exposure={"mode": "MCP_TOOL_EXPOSURE_MODE_ALL"})
        print("    TODO: create the server, then rerun")
        return None
    orq.mcp_servers.sync(id=server_id)
    print("    id", server_id)
    return server_id


def step_3_gateway(server_id: str | None) -> None:
    print(f"[3] MCP Gateway {GATEWAY_KEY}")
    # TODO: pick two read-only tool ids from GET /v2/mcp-servers/<id> (tools[]._id) and create the gateway:
    #   orq.mcp_gateways.create(key=GATEWAY_KEY, display_name=..., mode="MCP_GATEWAY_MODE_DIRECT",
    #       server_links=[{"mcp_server_id": server_id, "alias": "refund", "enabled": True,
    #                      "tool_exposure": {"mode": "MCP_TOOL_EXPOSURE_MODE_SELECTED", "tool_ids": [...]}}])
    print("    TODO")


def step_4_consume() -> None:
    url = f"{settings.base_url}/v3/mcp/{GATEWAY_KEY}"
    print("[4] MCP client ->", url)
    # TODO: headers={"Authorization": f"Bearer {settings.api_key}"}; list tools, call one, try the hidden one
    print("    TODO")


if __name__ == "__main__":
    settings.require_key()
    step_1_local_server()
    sid = step_2_register_server()
    step_3_gateway(sid)
    step_4_consume()
    if "--cleanup" in sys.argv:
        print("TODO: delete the gateway and the server (find ids with rest_id)")
