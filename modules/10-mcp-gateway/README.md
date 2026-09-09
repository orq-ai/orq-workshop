# 10 · MCP Gateway

!!! abstract "Factor 4: Tools are structured outputs, and Factor 10: Small, focused agents"
    The three refund tools return the same JSON whether the local loop, an MCP client or a managed agent calls them. The gateway decides which of them a given client is allowed to see. A small agent gets `lookup_order` and `get_policy`; nobody outside gets `issue_refund`.

**Time:** 30 min · **Prereqs:** module 00, `make seed` · **You will have:** the refund tools as an MCP server, an orq MCP Gateway `ws-refund-gateway` that exposes two of the three tools, a Python MCP client and a coding agent talking to it, and one managed-agent trace with an MCP tool span.

## Why

Tools leak. A coding agent that can look up orders can also refund them if both tools sit on the same server. The MCP Portal puts a governed endpoint between the client and the upstream server: one URL, an allow-list per server, every call logged with the exposed name, the upstream name, status, latency and the key that made it. Denied calls are logged as denied.

## The one concept to understand first

Three entities, one direction of trust.

```text
client (coding agent, agent, script)
   |  https://my.orq.ai/v3/mcp/<gateway-key>   Authorization: Bearer ORQ_API_KEY
   v
MCP Gateway  ws-refund-gateway     mode DIRECT, tool exposure SELECTED, alias "refund"
   |  server link -> tool_ids [lookup_order, get_policy]      issue_refund not exposed
   v
MCP Server   ws-refund-mcp         public upstream URL, auth NONE, synced tool catalogue
   |
   v
app/mcp_server.py                  MCPServer + @server.tool over app.refund_agent.tools
```

The MCP Server is the upstream registration. The Gateway is what clients connect to. The upstream URL must be reachable from orq: loopback and private addresses are rejected, so `http://127.0.0.1:8000/mcp` cannot be registered. Set `MCP_SERVER_URL` in `.env` to the deployed server. When it is empty the solution registers a public no-auth MCP server (DeepWiki, three read-only tools) as a stand-in so every step still runs.

## Steps

Start the local server in a second terminal and leave it running:

```bash
$ make mcp-server
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

`app/mcp_server.py` is 50 lines: an `MCPServer("lumen-refunds")`, one module-level `OrderStore`, three `@server.tool()` functions that call `app.refund_agent.tools`, and `server.run(transport="streamable-http", port=PORT, streamable_http_path="/mcp")`.

### Step 1 · Call the local server with an MCP client

```bash
$ uv run python modules/10-mcp-gateway/solution/run.py
```

Expected output (first block):

```text
[1] local MCP server http://127.0.0.1:8000/mcp
    server='lumen-refunds' protocol=2025-11-25
    tool lookup_order                     Look up an order owned by the current session user. Returns
    tool get_policy                       Fetch authoritative policy text. Topics: refund_basics, post
    tool issue_refund                     Issue a refund. Enforces ownership, no double refund, the EU
    call lookup_order({"order_id": "ord_a2"}) -> is_error=False
    {"ok": true, "order": {"id": "ord_a2", "amount": 89.0, "item": "Charging dock Duo", "delivered_days_ago": 15, "status": "delivered", "refunded": false, "within_standard_window": true}}
```

The client is the `mcp` package: `streamable_http_client(url)` gives the streams, `ClientSession(read, write)` does `initialize`, `list_tools`, `call_tool`. The tool result is the dict `tools.py` returns, serialised.

### Step 2 · Register the upstream server in the MCP Portal

```text
[2] MCP Portal server ws-refund-mcp -> https://mcp.deepwiki.com/mcp
    MCP_SERVER_URL is empty: using the public DeepWiki server as a stand-in for app/mcp_server.py
    id=mcp_server_01M21EYSRF22B1TGFX8X5591K7 sync=SYNC_STATUS_SYNCED tools=3 errors=[]
    tool ask_question             id=01M21F4K3Y81YZWV3T685EC43Y annotations=None
    tool read_wiki_contents       id=01M21F4K3Y81YZWV3T68DYJ2XJ annotations=None
    tool read_wiki_structure      id=01M21F4K3Y81YZWV3T6ASSX1AB annotations=None
```

`orq.mcp_servers.create(key=, display_name=, connection={"type": "MCP_CONNECTION_TYPE_HTTP", "url": ...}, auth={"type": "MCP_AUTH_TYPE_NONE"}, default_tool_exposure={"mode": "MCP_TOOL_EXPOSURE_MODE_ALL"})`, then `orq.mcp_servers.sync(id=)`. Sync discovers the tools and gives each one an id. With `MCP_SERVER_URL` set, the same block lists `lookup_order`, `get_policy`, `issue_refund`.

Try a tool from the CLI without a gateway in between:

```bash
$ orq mcp-servers test-tool mcp_server_01M21EYSRF22B1TGFX8X5591K7 --tool-name read_wiki_structure --arguments '{"repoName":"modelcontextprotocol/python-sdk"}'
```

### Step 3 · Create the gateway with two exposed tools

```text
[3] MCP Gateway ws-refund-gateway
    id=mcp_gateway_01M21F5H2NMA41DMEB7KER1AXP mode=MCP_GATEWAY_MODE_DIRECT exposed=2 public_url=https://my.orq.ai/v3/mcp/ws-refund-gateway
    exposed: ['read_wiki_structure', 'read_wiki_contents']   hidden: ['ask_question']
    read_wiki_contents                       <- ws-refund-mcp/read_wiki_contents
    read_wiki_structure                      <- ws-refund-mcp/read_wiki_structure
```

```python
orq.mcp_gateways.create(
    key="ws-refund-gateway", display_name="Refund gateway (workshop)", mode="MCP_GATEWAY_MODE_DIRECT",
    server_links=[{
        "mcp_server_id": server_id, "alias": "refund", "enabled": True,
        "tool_exposure": {"mode": "MCP_TOOL_EXPOSURE_MODE_SELECTED", "tool_ids": [lookup_order_id, get_policy_id]},
    }],
)
```

The last two lines of the block come from `orq mcp-gateways list-tools <gateway-id> --json`: the exposed name on the left, `server_key/upstream_tool_name` on the right. With the refund server the exposed pair is `lookup_order` and `get_policy`; `issue_refund` is not in `tool_ids`, so it does not exist for gateway clients.

### Step 4 · Consume the gateway from Python, then from a coding agent

```text
[4] MCP client -> https://my.orq.ai/v3/mcp/ws-refund-gateway
    server='orq-mcp-gateway' protocol=2024-11-05
    tool read_wiki_contents               View documentation about a GitHub repository.
    tool read_wiki_structure              Get a list of documentation topics for a GitHub repository.
    call read_wiki_structure({"repoName": "modelcontextprotocol/python-sdk"}) -> is_error=False
    Available pages for modelcontextprotocol/python-sdk:  - 1 Overview   - 1.1 Installation & Dependencies ...
    call ask_question -> MCPError: tool "ask_question" not found  (denied calls are logged too)
```

Same `mcp` client as step 1, plus a header: `create_mcp_http_client(headers={"Authorization": f"Bearer {ORQ_API_KEY}"})` passed as `http_client=`. The hidden tool is not "forbidden", it is absent: `tools/list` never returned it and `tools/call` answers `not found`.

A coding agent registers the same URL. Do not run this inside the workshop repo, it writes to your Claude config:

```bash
$ claude mcp add --transport http refund https://my.orq.ai/v3/mcp/ws-refund-gateway --header "Authorization: Bearer $ORQ_API_KEY"
$ claude mcp list
```

Now open **AI Gateway > MCP Portal > MCP Gateway > ws-refund-gateway**. The **Overview** tab shows tool calls, success, errors and P95 latency, and a leaderboard of exposed tools. Each logged call carries the exposed tool name, the upstream tool name, status, latency and the API key that made it. The `ask_question` call above appears there as a denied call.

### Step 5 · Give the managed agent one MCP tool

```text
[5] agent copy ws-refund-agent-mcp with an MCP tool
    settings.tools accepted: ['function', 'function', 'function', 'mcp']
    response id=resp_01M21FADDPKFCP3AE5P0KWQC23 trace=0cb8ee1e33a219ec1568a75cb6177f34 cost=0.0006015
    mcp_call server=ws-refund-mcp tool=read_wiki_structure status=completed args={"repoName":"modelcontextprotocol/python-sdk"}
    answer: The documentation topics for the GitHub repo **modelcontextprotocol/python-sdk** are as follows: ...
    span MCP Connect: ws-refund-mcp           type=span.tool status=ok 628.0ms
    span MCP Discover Tools: ws-refund-mcp    type=span.tool status=ok 149.0ms
    span chat openai/gpt-4o-mini              type=span.responses status=ok 708.0ms
    span read_wiki_structure                  type=span.tool status=ok 227.0ms
```

Agents attach to the MCP **Server**, not the gateway: `settings.tools` takes `{"type": "mcp", "key": "ws-refund-mcp", "tool_id": "<tool id from sync>"}`, one entry per tool. The agent then executes the tool server-side: the response contains an `mcp_call` output item, and the trace has an `MCP Connect` span, an `MCP Discover Tools` span and one `span.tool` per call. Nothing to run on your side. The gateway URL is for clients outside the platform.

The solution creates `ws-refund-agent-mcp` as a copy so `ws-refund-agent` stays as module 07 left it.

### Step 6 · Direct mode vs Code mode, and keys that cannot reach a gateway

- **Direct mode** exposes each upstream tool as its own MCP tool. Clients see `lookup_order` and `get_policy` directly. Best for small catalogues and for agents that need the schemas in context.
- **Code mode** exposes one gateway tool that does discovery and execution internally. Clients call it with code; the tool catalogue does not enter the model context. Best for gateways bundling dozens of servers.
- Switch in **Settings** on the gateway or with `orq.mcp_gateways.update(id=, mode=...)`. Tool naming (`MCP_TOOL_NAMING_PREFIX_WITH_SERVER_KEY` or `PREFIX_ON_COLLISION`) decides whether the alias prefixes every tool name.
- An API key can be pinned to gateways: `mcp_access={"allowed_mcp_gateway_ids": ["mcp_gateway_..."]}` allows only those, `mcp_access={"deny_all": True}` blocks every gateway, and `toolset_ids` narrows the key to a named toolset. Set it on `orq api-keys create` or `update`; this needs a Management Key, so treat it as an instructor demo.

### Cleanup

```bash
$ uv run python modules/10-mcp-gateway/solution/run.py --cleanup
```

Deletes `ws-refund-gateway`, `ws-refund-mcp` and `ws-refund-agent-mcp`. Keep them until you have done the coding-agent step.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Connect the `ws-refund-gateway` MCP gateway to this coding-agent session and use its `lookup_order` tool to check `ord_a2`. Then tell me which tools the gateway hides from you and why that is the point.

With the DeepWiki stand-in the agent sees `read_wiki_structure` and `read_wiki_contents` instead; ask it about `ask_question`. Either way the answer to "why" is the same: the client only gets the allow-list.

## Done when

- [ ] `make mcp-server` runs and the `[1]` block lists three tools
- [ ] **MCP Portal > MCP Servers** shows `ws-refund-mcp` as synced
- [ ] `orq mcp-gateways list-tools <id>` shows exactly two tools for `ws-refund-gateway`
- [ ] The gateway **Overview** shows your calls, including the denied one
- [ ] A trace of `ws-refund-agent-mcp` has a `span.tool` named after the MCP tool
- [ ] You can say why the agent attaches to the server and the coding agent to the gateway

## Gotchas

- `orq_ai_sdk 4.14.14` MCP models expect `id` but the API returns `_id`, so `orq.mcp_servers.create(...).mcp_server.id` and every tool `id` after `sync` are `None`. The solution reads the raw records with one `GET /v2/mcp-servers/<id>`. The CLI shows `_id` correctly.
- A server link without `"enabled": True` is stored disabled and exposes zero tools. The create call succeeds, `exposed_tools_count` is `0`.
- `tool_exposure.read_only: true` keeps only tools that carry a `readOnlyHint` annotation. DeepWiki's tools have none, so `read_only` alone hides everything. Use `tool_ids`.
- The upstream URL must be public. `ssh -R`, `cloudflared` or `ngrok` in front of `make mcp-server` work; loopback and RFC 1918 hosts are rejected by the API.
- Agents reference MCP tools by the server key plus a tool id, not by the gateway. Unverified: whether a gateway can be attached to an agent at all; the API has no field for it.
- `orq traces search` needs both `--from` and `--to` in 8.0.4. Use `orq.traces.list_spans(trace_id=)` with the `telemetry.trace_id` from the response instead.

## New in orq 4.14

The MCP Portal is new in 4.14: MCP Servers and MCP Gateway share one area, the old MCP Tool type is retired, every gateway call is logged with exposed and upstream name, and Management Keys can be scoped to MCP. Code Mode and Direct Mode are the two exposure modes of the same gateway.

## Go further

Create a **Toolset** on the gateway (a named subset of tools across servers) and bind an API key to it with `mcp_access.toolset_ids`. The key then sees only the intersection of what the gateway exposes and what the toolset contains, which is how one gateway serves several teams.
