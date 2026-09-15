"""Module 10 starter: the refund tools behind an orq MCP Gateway.

Tools leak. A coding agent that can look up orders can also refund them if both tools sit on
the same server. The MCP Portal puts a governed endpoint between the client and the upstream
server: one URL, an allow-list per server, every call logged. Four steps: call the local MCP
server, register it in the MCP Portal, create a gateway that exposes two of the three tools,
consume the gateway with a Bearer key.

Fill in the TODOs. The script runs as is; a step with an empty body prints what is missing.
Start the local server first (`make mcp-server`, app/mcp_server.py on http://127.0.0.1:8000/mcp),
then run `uv run python modules/10-mcp-gateway/run.py`. The solution is in `solution/run.py`.
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
    """Find a Portal record's id by key. Records carry `_id`; the SDK models drop it, so read it raw."""
    response = httpx.get(
        f"{settings.base_url}/v2/{kind}",
        params={"limit": 100},
        headers={"Authorization": f"Bearer {settings.api_key}"},
        timeout=30,
    )
    return next((record.get("_id") for record in response.json().get("data", []) if record.get("key") == key), None)


async def list_tools(url: str, headers: dict[str, str] | None = None) -> list[str]:
    """One MCP session: initialize, list tools. Hides the client/session nesting."""
    client = create_mcp_http_client(headers=headers) if headers else None
    async with streamable_http_client(url, http_client=client) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            # TODO: call lookup_order with {"order_id": "ord_a2"} via session.call_tool and print the result
            return [tool.name for tool in tools.tools]


# ── Step 1 · Call the local server with an MCP client ──
# app/mcp_server.py wraps the three refund tools in an MCPServer on :8000. Nothing orq-specific
# yet: the `mcp` client package lists and calls tools directly.
async def step_1_local_server() -> None:
    print("── Step 1 · Call the local server with an MCP client ──")
    print(f"url      : {LOCAL_URL}")
    try:
        names = await list_tools(LOCAL_URL)
    except Exception as exc:
        print(f"skipped  : not reachable ({type(exc).__name__}); run `make mcp-server` in another terminal, then rerun")
        return
    print(f"tools    : {', '.join(names)}")
    print("TODO     : call lookup_order inside `list_tools` and print its result, then rerun")
    print("next     : three tools, no allow-list; the gateway in step 3 decides who sees which")


# ── Step 2 · Register the upstream server in the MCP Portal ──
# The MCP Server is the upstream registration. `sync` discovers the tools and gives each an id.
# The URL must be public; without MCP_SERVER_URL the DeepWiki server stands in.
def step_2_register_server() -> str | None:
    upstream = settings.mcp_server_url or PUBLIC_FALLBACK_URL

    print("── Step 2 · Register the upstream server in the MCP Portal ──")
    print(f"server   : {SERVER_KEY} → {upstream}")
    server_id = rest_id("mcp-servers", SERVER_KEY)
    if server_id is None:
        # TODO: orq.mcp_servers.create(key=SERVER_KEY, display_name=..., connection={"type": "MCP_CONNECTION_TYPE_HTTP", "url": upstream},
        #       auth={"type": "MCP_AUTH_TYPE_NONE"}, default_tool_exposure={"mode": "MCP_TOOL_EXPOSURE_MODE_ALL"})
        print("TODO     : create the server with orq.mcp_servers.create, then rerun")
        return None
    orq.mcp_servers.sync(id=server_id)
    print(f"id       : {server_id}")
    print("next     : MCP Portal > MCP Servers shows the server as synced with its tool list")
    return server_id


# ── Step 3 · Create the gateway with two exposed tools ──
# The Gateway is what clients connect to: one server link with a SELECTED tool exposure. The
# third tool does not exist for gateway clients.
def step_3_gateway(server_id: str | None) -> None:
    print("── Step 3 · Create the gateway with two exposed tools ──")
    print(f"gateway  : {GATEWAY_KEY}")
    # TODO: pick two read-only tool ids from GET /v2/mcp-servers/<id> (tools[]._id) and create the gateway:
    #   orq.mcp_gateways.create(key=GATEWAY_KEY, display_name=..., mode="MCP_GATEWAY_MODE_DIRECT",
    #       server_links=[{"mcp_server_id": server_id, "alias": "refund", "enabled": True,
    #                      "tool_exposure": {"mode": "MCP_TOOL_EXPOSURE_MODE_SELECTED", "tool_ids": [...]}}])
    print("TODO     : create the gateway with two tool ids from the synced server, then rerun")
    print("next     : orq mcp-gateways list-tools <gateway id> should show exactly two tools")


# ── Step 4 · Consume the gateway from Python ──
# Same client as step 1 plus one header, Authorization: Bearer ORQ_API_KEY. The hidden tool is
# not forbidden, it is absent: tools/list never returns it and tools/call answers "not found".
async def step_4_consume() -> None:
    url = f"{settings.base_url}/v3/mcp/{GATEWAY_KEY}"

    print("── Step 4 · Consume the gateway from Python ───────────")
    print(f"url      : {url}")
    # TODO: headers={"Authorization": f"Bearer {settings.api_key}"}; list tools, call one, try the hidden one
    print("TODO     : list the gateway's tools with a Bearer header, call one, then call the hidden one, then rerun")
    print(f"next     : AI Gateway > MCP Portal > MCP Gateway > {GATEWAY_KEY} > Overview logs every call, denied ones included")


async def main() -> None:
    settings.require_key()
    await step_1_local_server()
    server_id = step_2_register_server()
    step_3_gateway(server_id)
    await step_4_consume()
    if "--cleanup" in sys.argv:
        print("TODO     : delete the gateway and the server (find their ids with rest_id)")


if __name__ == "__main__":
    asyncio.run(main())
