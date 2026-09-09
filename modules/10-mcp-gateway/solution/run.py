"""Module 10 solution: the refund tools as an MCP server, governed by an orq MCP Gateway.

Steps:
  1. call app/mcp_server.py locally with an MCP client
  2. register the upstream server in the MCP Portal and sync its tools
  3. create the gateway ws-refund-gateway exposing two read-only tools, Direct mode
  4. consume the gateway from Python with the MCP client (Authorization: Bearer ORQ_API_KEY)
  5. try to attach the gateway's tools to a copy of the managed agent
  6. (optional) --cleanup deletes the gateway, the server and the agent copy

The upstream URL must be public. Set MCP_SERVER_URL in .env to the deployed
app/mcp_server.py. Without it the run falls back to a public no-auth MCP server
(DeepWiki) so every step still produces real output.
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

orq = make_orq()
SERVER_KEY = settings.key("refund-mcp")
GATEWAY_KEY = settings.key("refund-gateway")
AGENT_COPY_KEY = settings.key("refund-agent-mcp")


# ---------------------------------------------------------------- helpers

def rest_get(path: str, **params: Any) -> dict[str, Any]:
    r = httpx.get(f"{settings.base_url}{path}", params=params, headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def rest_id(kind: str, key: str) -> str | None:
    """MCP Portal records carry `_id` (server, gateway, tool). orq_ai_sdk 4.14.14 models drop it: `.id` is None."""
    return next((d.get("_id") for d in rest_get(f"/v2/{kind}", limit=100).get("data", []) if d.get("key") == key), None)


async def mcp_list_and_call(url: str, headers: dict[str, str] | None = None, call: tuple[str, dict] | None = None) -> list[str]:
    """List tools on an MCP endpoint and optionally call one. Returns the tool names."""
    client = create_mcp_http_client(headers=headers) if headers else None
    async with streamable_http_client(url, http_client=client) as (read, write, *_):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"    server={init.server_info.name!r} protocol={init.protocol_version}")
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            for t in tools.tools:
                print(f"    tool {t.name:32s} {(t.description or '')[:60]}")
            if call:
                name, args = call
                res = await session.call_tool(name, args)
                body = res.content[0].text if res.content else ""
                print(f"    call {name}({json.dumps(args)}) -> is_error={res.is_error}")
                print("    " + body[:300].replace("\n", " "))
            return names
    if client:
        await client.aclose()


# ---------------------------------------------------------------- steps

def step_1_local_server() -> None:
    print("[1] local MCP server", LOCAL_URL)
    try:
        httpx.get(LOCAL_URL, timeout=2)
    except httpx.HTTPError:
        print("    not running. Start it in another terminal: make mcp-server")
        return
    asyncio.run(mcp_list_and_call(LOCAL_URL, call=("lookup_order", {"order_id": "ord_a2"})))


def step_2_register_server() -> Any:
    upstream = settings.mcp_server_url or PUBLIC_FALLBACK_URL
    print(f"[2] MCP Portal server {SERVER_KEY} -> {upstream}")
    if not settings.mcp_server_url:
        print("    MCP_SERVER_URL is empty: using the public DeepWiki server as a stand-in for app/mcp_server.py")
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
    state = server.get("sync_state") or {}
    print(f"    id={server_id} sync={state.get('status')} tools={state.get('tools_total')} errors={state.get('errors')}")
    for t in server.get("tools", []):
        print(f"    tool {t['name']:24s} id={t['_id']} annotations={t.get('annotations')}")
    return server


def step_3_gateway(server: Any) -> Any:
    print(f"[3] MCP Gateway {GATEWAY_KEY}")
    names = {t["name"]: t["_id"] for t in server.get("tools", [])}
    wanted = EXPOSE["refund"] if "lookup_order" in names else EXPOSE["deepwiki"]
    tool_ids = [names[n] for n in wanted if n in names] or list(names.values())[:2]
    hidden = sorted(set(names) - set(wanted))
    gateway_id = rest_id("mcp-gateways", GATEWAY_KEY)
    link = {
        "mcp_server_id": server["_id"],
        "alias": "refund",
        "enabled": True,  # the API stores enabled=false when omitted, and a disabled link exposes nothing
        # read_only=True would additionally require a readOnlyHint annotation on the upstream tool
        "tool_exposure": {"mode": "MCP_TOOL_EXPOSURE_MODE_SELECTED", "tool_ids": tool_ids},
    }
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
        gateway = orq.mcp_gateways.update(id=gateway_id, server_links=[link], mode="MCP_GATEWAY_MODE_DIRECT").mcp_gateway
    gateway.id = gateway_id
    print(f"    id={gateway_id} mode={gateway.mode} exposed={gateway.exposed_tools_count} public_url={gateway.public_url}")
    print(f"    exposed: {wanted}   hidden: {hidden}")
    out = subprocess.run(["orq", "mcp-gateways", "list-tools", gateway.id, "--json"], capture_output=True, text=True)
    for t in json.loads(out.stdout or "{}").get("data", []):
        print(f"    {t['exposed_name']:40s} <- {t['server_key']}/{t['upstream_tool_name']}")
    return gateway


def step_4_consume(gateway: Any) -> None:
    url = gateway.public_url if gateway.public_url.startswith("http") else f"{settings.base_url}{gateway.public_url}"
    print(f"[4] MCP client -> {url}")
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    names = asyncio.run(mcp_list_and_call(url, headers))
    upstream = {n.split("__")[-1].split(".")[-1]: n for n in names}
    pick = next((k for k in SAMPLE_CALL if k in upstream), None)
    if pick:
        asyncio.run(mcp_list_and_call(url, headers, call=(upstream[pick], SAMPLE_CALL[pick])))
    hidden = "issue_refund" if "lookup_order" in upstream else "ask_question"
    try:
        asyncio.run(mcp_list_and_call(url, headers, call=(hidden, {"repoName": "x/y", "question": "?", "order_id": "ord_a2", "reason": "x"})))
    except BaseException as exc:  # the mcp client raises an ExceptionGroup; the MCPError is inside
        while isinstance(exc, BaseExceptionGroup):
            exc = exc.exceptions[0]
        print(f"    call {hidden} -> {type(exc).__name__}: {str(exc)[:120]}  (denied calls are logged too)")
    print("    Studio: AI Gateway > MCP Portal > MCP Gateway > ws-refund-gateway > Overview shows the call")


def step_5_agent_copy(server: Any) -> None:
    """Attach one gateway-exposed MCP tool to a copy of the managed agent. UNVERIFIED shape; report what the API says."""
    print(f"[5] agent copy {AGENT_COPY_KEY} with an MCP tool")
    try:
        base = orq.agents.retrieve(agent_key=settings.key("refund-agent"))
    except Exception as exc:
        print(f"    base agent missing ({type(exc).__name__}); run make seed")
        return
    # retrieve() returns tools with `action_type`; create/update want `{"type": ..., "key": ...}`
    tools = [{"type": t.action_type, "key": t.key} for t in (base.settings.tools or [])] if base.settings else []
    by_name = {t["name"]: t["_id"] for t in server["tools"]}
    pick = "lookup_order" if "lookup_order" in by_name else "read_wiki_structure"
    # settings.tools MCP entry: parent = the MCP Portal server (by key), tool_id = one discovered tool's id
    mcp_entry = {"type": "mcp", "key": server["key"], "tool_id": by_name[pick]}
    question = "Look up order ord_a2." if pick == "lookup_order" else "List the documentation topics for the GitHub repo modelcontextprotocol/python-sdk. Use your tools."
    try:
        orq.agents.retrieve(agent_key=AGENT_COPY_KEY)
    except Exception:
        orq.agents.create(
            key=AGENT_COPY_KEY, display_name="Refund agent (mcp copy)", role=base.role, description=base.description,
            instructions=base.instructions, path=settings.path, model=settings.model,
            settings={"max_iterations": 8, "max_execution_time": 120, "tools": tools},
        )
    try:
        updated = orq.agents.update(agent_key=AGENT_COPY_KEY, settings={"tools": tools + [mcp_entry]})
        kinds = [getattr(t, "action_type", None) or getattr(t, "type", None) for t in updated.settings.tools]
        print(f"    settings.tools accepted: {kinds}")
        resp = orq.responses.create(model=f"agent/{AGENT_COPY_KEY}", input=question)
        d = resp.model_dump(exclude_none=True)
        trace_id = (d.get("telemetry") or {}).get("trace_id")
        print(f"    response id={d['id']} trace={trace_id} cost={(d.get('usage') or {}).get('total_cost')}")
        for o in d.get("output", []):
            if o.get("type") == "mcp_call":
                print(f"    mcp_call server={o['server_name']} tool={o['tool_name']} status={o['status']} args={o['arguments'][:60]}")
            elif o.get("content"):
                print("    answer: " + str(o["content"][0].get("text", ""))[:160].replace("\n", " "))
        for sp in (orq.traces.list_spans(trace_id=trace_id).data or []) if trace_id else []:
            sd = sp.model_dump(exclude_none=True)
            print(f"    span {sd.get('name', '')[:36]:36s} type={sd.get('type')} status={sd.get('status')} {sd.get('duration_ms')}ms")
    except Exception as exc:
        print(f"    UNVERIFIED: {type(exc).__name__}: {str(exc)[:300]}")


def cleanup() -> None:
    print("[cleanup]")
    if gid := rest_id("mcp-gateways", GATEWAY_KEY):
        orq.mcp_gateways.delete(id=gid); print(f"    deleted gateway {GATEWAY_KEY}")
    if sid := rest_id("mcp-servers", SERVER_KEY):
        orq.mcp_servers.delete(id=sid); print(f"    deleted server {SERVER_KEY}")
    try:
        orq.agents.delete(agent_key=AGENT_COPY_KEY); print(f"    deleted agent {AGENT_COPY_KEY}")
    except Exception:
        pass


if __name__ == "__main__":
    settings.require_key()
    step_1_local_server()
    server = step_2_register_server()
    gateway = step_3_gateway(server)
    step_4_consume(gateway)
    step_5_agent_copy(server)
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        print(f"kept {GATEWAY_KEY} for the coding-agent step. Remove with: uv run python modules/10-mcp-gateway/solution/run.py --cleanup")
