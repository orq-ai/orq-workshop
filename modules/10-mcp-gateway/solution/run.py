"""Module 10: the refund tools as an MCP server, governed by an orq MCP Gateway.

Tools leak. A coding agent that can look up orders can also refund them if both tools sit on
the same server. The MCP Portal puts a governed endpoint between the client and the upstream
server: one URL, an allow-list per server, every call logged with the exposed name, the upstream
name and the key that made it. Five steps: call app/mcp_server.py locally with an MCP client,
register the upstream server in the MCP Portal and sync its tools, create the gateway
ws-refund-gateway exposing two read-only tools (Direct mode), consume the gateway from Python
with a Bearer key, and attach one synced tool to a copy of the managed agent. `--cleanup`
deletes the gateway, the server and the agent copy.

The upstream URL must be public. Set MCP_SERVER_URL in .env to the deployed app/mcp_server.py.
Without it the run falls back to a public no-auth MCP server (DeepWiki) so every step still
produces real output.

Run it with `uv run python modules/10-mcp-gateway/solution/run.py` (or `make m10`), with
`make mcp-server` running in another terminal for step 1.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

LOCAL_URL = "http://127.0.0.1:8000/mcp"
PUBLIC_FALLBACK_URL = "https://mcp.deepwiki.com/mcp"  # no auth, three read-only tools
# Two tools to expose per upstream; the third tool of each server stays hidden on purpose.
EXPOSE = {
    "refund": ["lookup_order", "get_policy"],  # hides issue_refund
    "deepwiki": ["read_wiki_structure", "read_wiki_contents"],  # hides ask_question
}
SAMPLE_CALL = {
    "lookup_order": {"order_id": "ord_a2"},
    "read_wiki_structure": {"repoName": "modelcontextprotocol/python-sdk"},
}
# One argument set that fits both hidden tools, so the denied call is a real call either way.
HIDDEN_CALL_ARGS = {"repoName": "x/y", "question": "?", "order_id": "ord_a2", "reason": "x"}

orq = make_orq()
SERVER_KEY = settings.key("refund-mcp")
GATEWAY_KEY = settings.key("refund-gateway")
AGENT_COPY_KEY = settings.key("refund-agent-mcp")
STUDIO_GATEWAY = f"AI Gateway > MCP Portal > MCP Gateway > {GATEWAY_KEY}"


def rest_get(path: str, **params: Any) -> dict[str, Any]:
    """One authenticated GET against the REST API, for the fields the SDK models drop."""
    response = httpx.get(
        f"{settings.base_url}{path}",
        params=params,
        headers={"Authorization": f"Bearer {settings.api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def rest_id(kind: str, key: str) -> str | None:
    """Find a Portal record's id by key. Records carry `_id`; orq_ai_sdk 4.14.14 models drop it, so `.id` is None."""
    records = rest_get(f"/v2/{kind}", limit=100).get("data", [])
    return next((record.get("_id") for record in records if record.get("key") == key), None)


async def mcp_list_and_call(
    url: str,
    headers: dict[str, str] | None = None,
    call: tuple[str, dict] | None = None,
    show_tools: bool = True,
) -> list[str]:
    """One MCP session: initialize, list tools, optionally call one. Hides the client/session nesting."""
    client = create_mcp_http_client(headers=headers) if headers else None
    try:
        async with streamable_http_client(url, http_client=client) as (read, write, *_):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                print(f"server   : {init.server_info.name!r} protocol={init.protocol_version}")
                tools = await session.list_tools()
                names = [tool.name for tool in tools.tools]
                if show_tools:
                    for tool in tools.tools:
                        print(f"tool     : {tool.name:<32} {(tool.description or '')[:60]}")
                if call:
                    name, args = call
                    outcome = await session.call_tool(name, args)
                    body = outcome.content[0].text if outcome.content else ""
                    print(f"call     : {name}({json.dumps(args)}) → is_error={outcome.is_error}")
                    print(f"result   : {body[:300].replace(chr(10), ' ')}")
                return names
    finally:
        if client:
            await client.aclose()


# ── Step 1 · Call the local server with an MCP client ──
# app/mcp_server.py wraps the three refund tools in an MCPServer on :8000. The `mcp` client
# package gives the streams; ClientSession does initialize, list_tools and call_tool. The tool
# result is the dict tools.py returns, serialised. Nothing orq-specific yet.
async def step_1_local_server() -> None:
    print("── Step 1 · Call the local server with an MCP client ──")
    print(f"url      : {LOCAL_URL}")
    try:
        httpx.get(LOCAL_URL, timeout=2)
    except httpx.HTTPError:
        print("skipped  : not running. Start it in another terminal: make mcp-server, then rerun")
        return
    await mcp_list_and_call(LOCAL_URL, call=("lookup_order", SAMPLE_CALL["lookup_order"]))
    print("next     : three tools, no allow-list; the gateway in step 3 decides who sees which")


# ── Step 2 · Register the upstream server in the MCP Portal ──
# The MCP Server is the upstream registration: a public URL, an auth mode and a default tool
# exposure. `sync` discovers the tools and gives each one an id, which step 3 and step 5 refer
# to. Loopback and private addresses are rejected, so without MCP_SERVER_URL the public
# DeepWiki server stands in for app/mcp_server.py.
def step_2_register_server() -> Any:
    upstream = settings.mcp_server_url or PUBLIC_FALLBACK_URL

    print("── Step 2 · Register the upstream server in the MCP Portal ──")
    print(f"server   : {SERVER_KEY} → {upstream}")
    if not settings.mcp_server_url:
        print("note     : MCP_SERVER_URL is empty: using the public DeepWiki server as a stand-in for app/mcp_server.py")
    server_id = rest_id("mcp-servers", SERVER_KEY)
    if server_id is None:
        orq.mcp_servers.create(
            key=SERVER_KEY,
            display_name="Refund tools (workshop)",
            description="app/mcp_server.py, or a public stand-in when MCP_SERVER_URL is empty",
            connection={"type": "MCP_CONNECTION_TYPE_HTTP", "url": upstream},
            auth={"type": "MCP_AUTH_TYPE_NONE"},
            default_tool_exposure={"mode": "MCP_TOOL_EXPOSURE_MODE_ALL"},
        )
        server_id = rest_id("mcp-servers", SERVER_KEY)
    orq.mcp_servers.sync(id=server_id)
    server = rest_get(f"/v2/mcp-servers/{server_id}")  # raw: tool ids live in `_id`
    server = server.get("mcp_server", server)
    sync_state = server.get("sync_state") or {}
    print(f"id       : {server_id}")
    print(f"sync     : {sync_state.get('status')} tools={sync_state.get('tools_total')} errors={sync_state.get('errors')}")
    for tool in server.get("tools", []):
        print(f"tool     : {tool['name']:<24} id={tool['_id']} annotations={tool.get('annotations')}")
    print(f"next     : try one without a gateway: orq mcp-servers test-tool {server_id} --tool-name <name> --arguments '{{...}}'")
    return server


# ── Step 3 · Create the gateway with two exposed tools ──
# The Gateway is what clients connect to. One server link, alias `refund`, and a SELECTED tool
# exposure with two tool ids: the third tool does not exist for gateway clients. Direct mode
# exposes each upstream tool as its own MCP tool. Re-running updates the link instead of
# creating a second gateway.
def step_3_gateway(server: Any) -> Any:
    tool_ids_by_name = {tool["name"]: tool["_id"] for tool in server.get("tools", [])}
    wanted = EXPOSE["refund"] if "lookup_order" in tool_ids_by_name else EXPOSE["deepwiki"]
    tool_ids = [tool_ids_by_name[name] for name in wanted if name in tool_ids_by_name]
    tool_ids = tool_ids or list(tool_ids_by_name.values())[:2]  # unknown upstream: expose the first two
    hidden = sorted(set(tool_ids_by_name) - set(wanted))
    link = {
        "mcp_server_id": server["_id"],
        "alias": "refund",
        "enabled": True,  # the API stores enabled=false when omitted, and a disabled link exposes nothing
        # read_only=True would additionally require a readOnlyHint annotation on the upstream tool
        "tool_exposure": {"mode": "MCP_TOOL_EXPOSURE_MODE_SELECTED", "tool_ids": tool_ids},
    }

    print("── Step 3 · Create the gateway with two exposed tools ──")
    gateway_id = rest_id("mcp-gateways", GATEWAY_KEY)
    if gateway_id is None:
        gateway = orq.mcp_gateways.create(
            key=GATEWAY_KEY,
            display_name="Refund gateway (workshop)",
            description="Two read-only refund tools. issue_refund stays behind the gateway.",
            server_links=[link],
            mode="MCP_GATEWAY_MODE_DIRECT",
        ).mcp_gateway
        gateway_id = rest_id("mcp-gateways", GATEWAY_KEY)
    else:
        gateway = orq.mcp_gateways.update(
            id=gateway_id, server_links=[link], mode="MCP_GATEWAY_MODE_DIRECT"
        ).mcp_gateway
    gateway.id = gateway_id  # the SDK model drops `_id`; the CLI call below needs it
    print(f"gateway  : {GATEWAY_KEY} ({gateway_id})")
    print(f"mode     : {gateway.mode} exposed={gateway.exposed_tools_count}")
    print(f"url      : {gateway.public_url}")
    print(f"exposed  : {', '.join(wanted)}")
    print(f"hidden   : {', '.join(hidden)}")
    listing = subprocess.run(
        ["orq", "mcp-gateways", "list-tools", gateway.id, "-o", "json"],
        capture_output=True,
        text=True,
    )
    for tool in json.loads(listing.stdout or "{}").get("data", []):
        print(f"tool     : {tool['exposed_name']:<40} ← {tool['server_key']}/{tool['upstream_tool_name']}")
    print("next     : the tool lines come from `orq mcp-gateways list-tools`: exposed name ← server_key/upstream name")
    return gateway


# ── Step 4 · Consume the gateway from Python ──
# Same client as step 1 plus one header, Authorization: Bearer ORQ_API_KEY. Three sessions:
# list the tools, call an exposed one, call the hidden one. The hidden tool is not forbidden,
# it is absent: tools/list never returned it and tools/call answers "not found". Both the
# successful and the denied call are logged on the gateway.
async def step_4_consume(gateway: Any) -> None:
    url = gateway.public_url if gateway.public_url.startswith("http") else f"{settings.base_url}{gateway.public_url}"
    headers = {"Authorization": f"Bearer {settings.api_key}"}

    print("── Step 4 · Consume the gateway from Python ───────────")
    print(f"url      : {url}")
    names = await mcp_list_and_call(url, headers)
    # Exposed names may be prefixed with the alias (refund__lookup_order); map back to the upstream name.
    upstream_by_name = {name.split("__")[-1].split(".")[-1]: name for name in names}
    sample = next((name for name in SAMPLE_CALL if name in upstream_by_name), None)
    if sample:
        await mcp_list_and_call(url, headers, call=(upstream_by_name[sample], SAMPLE_CALL[sample]), show_tools=False)
    hidden = "issue_refund" if "lookup_order" in upstream_by_name else "ask_question"
    try:
        await mcp_list_and_call(url, headers, call=(hidden, HIDDEN_CALL_ARGS), show_tools=False)
    except BaseException as exc:  # the mcp client raises an ExceptionGroup; the MCPError is inside
        while isinstance(exc, BaseExceptionGroup):
            exc = exc.exceptions[0]
        print(f"denied   : {hidden} → {type(exc).__name__}: {str(exc)[:120]}")
    print(f"next     : {STUDIO_GATEWAY} > Overview shows both calls, the denied one included")


# ── Step 5 · Give the managed agent one MCP tool ──
# Agents attach to the MCP Server, not the gateway: settings.tools takes
# {"type": "mcp", "key": <server key>, "tool_id": <id from sync>}, one entry per tool. The agent
# then runs the tool server-side: the response carries an mcp_call output item and the trace
# has MCP Connect, MCP Discover Tools and one span.tool per call. A copy of ws-refund-agent
# keeps module 07's agent untouched. UNVERIFIED shape: the block reports what the API says.
def step_5_agent_copy(server: Any) -> None:
    print("── Step 5 · Give the managed agent one MCP tool ───────")
    print(f"agent    : {AGENT_COPY_KEY} (copy of {settings.key('refund-agent')})")
    try:
        base = orq.agents.retrieve(agent_key=settings.key("refund-agent"))
    except Exception as exc:
        print(f"skipped  : base agent missing ({type(exc).__name__}); run make seed")
        return
    # retrieve() returns tools with `action_type`; create/update want `{"type": ..., "key": ...}`
    tools = [{"type": tool.action_type, "key": tool.key} for tool in (base.settings.tools or [])] if base.settings else []
    tool_ids_by_name = {tool["name"]: tool["_id"] for tool in server["tools"]}
    pick = "lookup_order" if "lookup_order" in tool_ids_by_name else "read_wiki_structure"
    # settings.tools MCP entry: parent = the MCP Portal server (by key), tool_id = one discovered tool's id
    mcp_entry = {"type": "mcp", "key": server["key"], "tool_id": tool_ids_by_name[pick]}
    question = (
        "Look up order ord_a2."
        if pick == "lookup_order"
        else "List the documentation topics for the GitHub repo modelcontextprotocol/python-sdk. Use your tools."
    )
    print(f"mcp tool : {json.dumps(mcp_entry)}")
    try:
        orq.agents.retrieve(agent_key=AGENT_COPY_KEY)
    except Exception:
        orq.agents.create(
            key=AGENT_COPY_KEY,
            display_name="Refund agent (mcp copy)",
            role=base.role,
            description=base.description,
            instructions=base.instructions,
            path=settings.path,
            model=settings.model,
            settings={"max_iterations": 8, "max_execution_time": 120, "tools": tools},
        )
    try:
        updated = orq.agents.update(agent_key=AGENT_COPY_KEY, settings={"tools": tools + [mcp_entry]})
        kinds = [getattr(tool, "action_type", None) or getattr(tool, "type", None) for tool in updated.settings.tools]
        print(f"tools    : {', '.join(str(kind) for kind in kinds)}")
        print(f"question : {question}")
        response = orq.responses.create(model=f"agent/{AGENT_COPY_KEY}", input=question)
        payload = response.model_dump(exclude_none=True)
        trace_id = (payload.get("telemetry") or {}).get("trace_id")
        print(f"response : {payload['id']} cost={(payload.get('usage') or {}).get('total_cost')}")
        for item in payload.get("output", []):
            if item.get("type") == "mcp_call":
                print(f"mcp_call : server={item['server_name']} tool={item['tool_name']} status={item['status']} args={item['arguments'][:60]}")
            elif item.get("content"):
                print(f"answer   : {str(item['content'][0].get('text', ''))[:160].replace(chr(10), ' ')}")
        print(f"trace    : {trace_id}")
        spans = (orq.traces.list_spans(trace_id=trace_id).data or []) if trace_id else []
        for span in spans:
            span_data = span.model_dump(exclude_none=True)
            print(f"span     : {span_data.get('name', '')[:36]:<36} type={span_data.get('type')} status={span_data.get('status')} {span_data.get('duration_ms')}ms")
        print("next     : the MCP Connect and Discover Tools spans are the agent reaching the server; the span.tool is the call")
    except Exception as exc:
        print(f"verdict  : UNVERIFIED: {type(exc).__name__}: {str(exc)[:300]}")


# ── Cleanup (only with --cleanup) ──
# Deletes the three entities this module created. Keep them until the coding-agent step is done.
def cleanup() -> None:
    print("── Cleanup ────────────────────────────────────────────")
    if gateway_id := rest_id("mcp-gateways", GATEWAY_KEY):
        orq.mcp_gateways.delete(id=gateway_id)
        print(f"deleted  : gateway {GATEWAY_KEY}")
    if server_id := rest_id("mcp-servers", SERVER_KEY):
        orq.mcp_servers.delete(id=server_id)
        print(f"deleted  : server {SERVER_KEY}")
    try:
        orq.agents.delete(agent_key=AGENT_COPY_KEY)
        print(f"deleted  : agent {AGENT_COPY_KEY}")
    except Exception:
        pass  # the copy is only created when step 5 got that far


async def main() -> None:
    settings.require_key()
    await step_1_local_server()
    server = step_2_register_server()
    gateway = step_3_gateway(server)
    await step_4_consume(gateway)
    step_5_agent_copy(server)
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        print(f"kept {GATEWAY_KEY} for the coding-agent step. Remove with: uv run python modules/10-mcp-gateway/solution/run.py --cleanup")


if __name__ == "__main__":
    asyncio.run(main())
