# 08 · Managed agents

!!! abstract "The agent lives in orq, your code executes the tools"
    The agent lives in orq. Your code is the tool executor: every `function_call` item comes back to you, you answer it, the conversation resumes server-side. One agent, three tools, eight iterations max.

| | |
|---|---|
| **Time** | 40 min |
| **Prerequisites** | modules 00 to 02, `make seed` |
| **You will have** | the refund agent invoked through the Responses API from Python, curl and the CLI, with a local tool loop, streamed, carrying variables and metadata, continued across turns, tool calls steered with `tool_choice`, given memory, versioned and pinned by `@version`. |

## Why

Modules 01 to 07 kept the agent loop in `app/refund_agent/agent.py`. This module moves the loop to orq: instructions, model, tool schemas, iteration and time limits, knowledge base and memory are one entity with versions. The app shrinks to "execute this tool call and send the result back". That is the split the Responses API is built for, and it is what the Studio, the CLI and the coding-agent skills operate on.

## The one concept to understand first

A managed agent does not run your Python. When it decides to call `lookup_order`, the response comes back `status: completed` with a `function_call` output item and stops. You execute it, then continue the same response chain:

```python
from orq_ai_sdk import Orq

orq = Orq(api_key=os.environ["ORQ_API_KEY"])          # app/refund_agent/client.py: make_orq()
r = orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please")
call = r.output[0]                                   # type=function_call, name, arguments, call_id
result = dispatch(store, call.name, json.loads(call.arguments))
r = orq.responses.create(
    model="agent/ws-refund-agent",
    previous_response_id=r.id,                       # server-side state, no history resent
    input=[{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)}],
)
```

![Diagram: the Responses API tool loop. Your app calls responses.create on agent/ws-refund-agent; the agent runs the model and returns a function_call item with a call_id; your app executes it with tools.dispatch and sends a function_call_output with previous_response_id; the loop repeats until a message item with a trace id comes back.](assets/responses-tool-loop.png)

Match on `call_id`, not `id`. Server-side tools (memory, advisor, `current_date`) also emit a `function_call` item, followed by an `orq:<tool>` item carrying the result; those are not yours to answer. Every call returns `telemetry.trace_id`.

## Steps

Open `modules/08-managed-agents/run.py`. The loop in `run_agent` has two `TODO`s, and steps 4 to 6 one each. The solution is in `solution/run.py`. The steps follow the [Run Agents](https://docs.orq.ai/docs/ai-studio/ai-engineering/run-agents) docs page: every call is shown in Python, and where it fits, as curl and as the `orq` CLI, all three against the same `POST /v3/router/responses`.

### Step 1 · Inspect the agent

```bash
$ orq agents retrieve ws-refund-agent -o json | jq '{key, version, model: .model.id, settings: {max_iterations: .settings.max_iterations, max_execution_time: .settings.max_execution_time, tool_approval_required: .settings.tool_approval_required, tools: [.settings.tools[] | {action_type, key, requires_approval}]}, knowledge_bases}'
$ make m08      # the solution; the starter prints the same block once its TODOs are filled in
```

Expected output:

```text
── Step 1 · Inspect the agent ─────────────────────────
agent    : ws-refund-agent v1.1.0 (live)
model    : openai/gpt-5.6-luna
limits   : max_iterations 8, max_execution_time 120s
approval : tool_approval_required=respect_tool
tools    : [('function', 'ws-lookup-order', 'S4GC7Z'), ('function', 'ws-issue-refund', '7NXF3X'), ('function', 'ws-get-policy', 'Z2QE66'), ('retrieve_knowledge_bases', 'Retrieve Knowledge Bases', '55XZ86'), ('query_knowledge_base', 'Query Knowledge Base', 'X018W4')]  (action_type, key, id suffix: the READ shape)
kb       : [{'knowledge_id': '01M2K8Y4HRF33KBXZVMTQVM6KB'}]
memory   : []
patch    : rejected, ValueError: Could not find discriminator field type in {'id': '01M2K8Y61FFSQ5BE3BV…
write    : settings.tools = [{'type': 'function', 'key': 'ws-lookup-order'}, ...]
next     : open Agents > ws-refund-agent in the Studio; the Versions tab is used in step 8
```

Reads and writes have different shapes. A GET returns tools as `{action_type, id, key, requires_approval}`; a create or update wants `{"type": "function", "key": "ws-lookup-order"}`. Inline function schemas are rejected: register the tool once (`orq tools create`), then reference it by key. Open the agent in the Studio (**Agents** > `ws-refund-agent`): the same instructions, the tool list, the limits, and a **Versions** tab.

### Step 2 · Invoke it: Python SDK, curl, CLI

One question, three clients. The Python SDK:

```python
response = orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please, the dock does not fit.")
```

curl, the same body:

```bash
$ curl -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent", "input": "Refund ord_a2 please, the dock does not fit."}'
```

The CLI:

```bash
$ orq responses create --model agent/ws-refund-agent --input '"Refund ord_a2 please, the dock does not fit."' -o json
```

All three return the same response object: `id`, `status: completed`, `output[]` and `telemetry.trace_id`. For this question the first `output` item is a `function_call`, so the turn is not over: `run_agent` executes it and continues, four requests in total.

```text
── Step 2 · Invoke it and execute the tool calls ──────
question : Refund ord_a2 please, the dock does not fit.
tools    : lookup_order → get_policy → issue_refund
requests : 4 in 4.5s, cost $0.00007
answer   : Your refund of **€89.00** for the charging dock has been processed to the original payment method. P…
first    : 06fd53186e9a2ea2ed92fab1a22017a4
last     : 523e86384f5756caac784033b06cc2f3
next     : run `orq traces thread 523e86384f5756caac784033b06cc2f3`; the last trace renders the whole conversation
```

Four requests, four traces: each Responses call is its own trace with an `agent.response` span and a `chat openai/gpt-5.6-luna` span. State is server-side, so the last trace's thread view is the conversation as the customer saw it; the tool calls and their results sit in the three traces before it:

```console
$ orq traces thread c4e68bf2a8a0e9814b9e08eb9dabb93c --slice -2:
<thread trace="c4e68bf2a8a0e9814b9e08eb9dabb93c" span="26b1f583bbd66a49" format="responses" model="gpt-5.6-luna" duration_ms="1398" tokens="1343">

<message index="0" role="user">
Refund ord_a2 please, the dock does not fit.
</message>

<message index="1" role="assistant">
Your refund of **€89** for the charging dock has been issued to the original payment method. It should arrive within **5–7 business days**.
</message>

</thread>
```

From curl the continuation is the same two-step cycle: `previous_response_id` plus a `function_call_output` item keyed on `call_id`:

```bash
$ curl -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent", "previous_response_id": "resp_...",
       "input": [{"type": "function_call_output", "call_id": "call_...", "output": "{\"ok\": true, \"order\": {...}}"}]}'
```

If a model confirms the order first and waits ("Would you like to proceed?"), the turn ends with two tool calls and no refund. The fixed instructions say the request is the confirmation; a prompt that asks for one needs a second turn before `issue_refund` shows up.

### Step 3 · Stream

`stream=True` returns an event stream; from curl it is `"stream": true` with `-N`, from the CLI `--stream`. Text arrives as `response.output_text.delta` events; a `function_call` arrives as `response.function_call_arguments.delta` and `.done`, and the complete item, with `arguments` and `call_id` ready for the continuation, on `response.output_item.done`. A prompt the agent answers with a tool call streams no text at all (luna fetches `get_policy` for "what is the refund window?"), so the step asks something the agent answers by itself.

```bash
$ curl -N -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent", "input": "Say hello in one sentence.", "stream": true}'
```

| Event | When | Key field |
|---|---|---|
| `response.created` | stream opens | `id`, the `previous_response_id` for the next turn |
| `response.output_text.delta` | each text chunk | `delta` |
| `response.output_text.done` | text complete | `text` |
| `response.output_item.done` | an output item is complete | `item`, the full `function_call` when it is one |
| `response.completed` | agent finished | `response.status` |
| `response.failed` | error | `response.error` |

```text
── Step 3 · Stream ────────────────────────────────────
events   : 17
first    : token at 0.71s
tokens   : ['Hello', '!', ' How', ' can', ' I', ' help']
text     : Hello! How can I help you today?
next     : the first token arrived well before the full text; that is what a chat UI renders
```

The CLI does the same: `orq responses create --model agent/ws-refund-agent --input '"..."' --stream`. (`orq agents stream` still exists; it speaks the older A2A shape and the SDK marks it deprecated.)

### Step 4 · Variables, metadata, identity, thread

Four request fields that change nothing in the agent and everything in what you can find later. `variables` fill `{{placeholders}}` in the instructions and in the input; the seeded instructions have none, so this step puts one in the input. `metadata` is free-form string pairs, echoed on the response and stored on the trace. `identity` and `thread` are not echoed; they land on the trace as `identity_id` and `thread_id`, which is what groups traces into customers and conversations in the Studio.

```python
tagged = orq.responses.create(
    model="agent/ws-refund-agent",
    input="My name is {{customer_name}}. Greet me by name in one sentence, nothing else.",
    variables={"customer_name": "Jane Okafor"},
    metadata={"session_id": "sess-ws-1", "channel": "chat"},
    identity={"id": "customer-user_001"},
    thread={"id": "conv-ws-1"},
)
```

```bash
$ curl -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent",
       "input": "My name is {{customer_name}}. Greet me by name in one sentence, nothing else.",
       "variables": {"customer_name": "Jane Okafor"},
       "metadata": {"session_id": "sess-ws-1", "channel": "chat"},
       "identity": {"id": "customer-user_001"}, "thread": {"id": "conv-ws-1"}}'
$ orq responses create --model agent/ws-refund-agent --input '"My name is {{customer_name}}. Greet me by name in one sentence, nothing else."' \
    --variables customer_name="Jane Okafor" --metadata session_id=sess-ws-1 --metadata channel=chat \
    --identity '{"id": "customer-user_001"}' --thread '{"id": "conv-ws-1"}' -o json
```

```text
── Step 4 · Variables, metadata, identity, thread ─────
answer   : Hello, Jane Okafor!
variables: {'customer_name': 'Jane Okafor'}  (echoed; the placeholder was rendered server-side)
metadata : {'channel': 'chat', 'session_id': 'sess-ws-1'}  (echoed, and stored on the trace)
identity : not echoed; thread: not echoed  (both land on the trace)
trace    : 88fa5f5072c149abf2e9b2d647c50211
next     : orq traces get 88fa5f5072c149abf2e9b2d647c50211 -o json | jq '.trace | {identity_id, thread_id, metadata: .attributes.metadata}'
```

Metadata values must be strings (a number is a 400). A variable can also be a secret, `{"secret": true, "value": "..."}`: it is passed to platform tools and redacted from traces. To put placeholders in the agent itself, see the Build Agents docs on variables and templates.

### Step 5 · Continue a conversation

`previous_response_id` is not only for tool results. Send it with a new user message and the agent answers with the whole conversation in context, server-side, nothing resent. Any stored response can be fetched again with `orq.responses.get`, and `background=True` returns at once with `status: queued`, so that same `get` doubles as polling.

```python
first = run_agent("ws-refund-agent", "Refund ord_a2 please, the dock does not fit.")
follow_up = orq.responses.create(model="agent/ws-refund-agent", previous_response_id=first["response_id"], input="Thanks. What was the refund amount, digits only?")
fetched = orq.responses.get(response_id=follow_up.id)
queued = orq.responses.create(model="agent/ws-refund-agent", input="Say hello in one sentence.", background=True)   # status: queued
```

```bash
$ curl -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent", "previous_response_id": "resp_...", "input": "Thanks. What was the refund amount, digits only?"}'
$ curl https://my.orq.ai/v3/router/responses/resp_... -H "Authorization: Bearer $ORQ_API_KEY"
$ orq responses create --model agent/ws-refund-agent --previous-response-id resp_... --input '"Thanks. What was the refund amount, digits only?"'
$ orq responses get resp_...
```

```text
── Step 5 · Continue a conversation ───────────────────
turn 1   : Your refund of **€89** for order **ord_a2** has been issued to the original paym…  (lookup_order → get_policy → issue_refund)
turn 2   : '89'  via previous_response_id=resp_01M2MVV8ZH7FCMZ8JDQM7BVSR3
get      : resp_01M2MVVADCXV02Y4VGAZ2BM10V status completed, 1 output item(s), same text: True
background: created with status queued, polled to completed in 1.2s: 'Hello! How can I help you today?'
next     : orq responses get resp_01M2MVVADCXV02Y4VGAZ2BM10V -o json | jq '.output[0].content[0].text'
```

`previous_response_id` needs the earlier response stored (`store` defaults to true). A background response that ends in a tool call has no text yet: read `output[].type` before `content`.

### Step 6 · Control tool calls

`tool_choice` steers the agent's own tools: `"none"` forbids them, `"required"` forces at least one, `{"type": "function", "name": "get_policy"}` forces a named one. A `tools` array in the request is accepted, echoed and ignored on an `agent/` call: an agent's tools come from its configuration, MCP and HTTP tools included ([module 10](https://orq-ai.github.io/orq-workshop/modules/10/), [module 15](https://orq-ai.github.io/orq-workshop/modules/15/)). Built-in tools (`orq:current_date` in SDK 4.14, `orq:datetime` in the docs) follow the same rule: attach them to the agent.

```python
orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please, the dock does not fit.", tool_choice="none")
orq.responses.create(model="agent/ws-refund-agent", input="Hello!", tool_choice="required")
orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please.", tool_choice={"type": "function", "name": "get_policy"})
```

```bash
$ curl -X POST https://my.orq.ai/v3/router/responses \
  -H "Authorization: Bearer $ORQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agent/ws-refund-agent", "input": "Refund ord_a2 please, the dock does not fit.", "tool_choice": "none"}'
$ orq responses create --model agent/ws-refund-agent --input '"Refund ord_a2 please."' --tool-choice '{"type": "function", "name": "get_policy"}'
```

```text
── Step 6 · Control tool calls ────────────────────────
none     : ['message']
required : ['reasoning', 'function_call:get_policy']
get_policy: ['reasoning', 'function_call:get_policy']
req tools: ['message']  (get_weather echoed on the response, never called: agent tools are configuration)
next     : `required` on a plain greeting forced a tool the agent did not need; which one varies per run (get_policy or a knowledge tool)
```

With `tool_choice="none"` the agent explains it cannot look the order up: the refusal is the instructions working without tools. `required` on a greeting is the anti-pattern the docs warn about; use it for a retrieval step that must always run.

### Step 7 · Memory

A memory store is an embedding-backed store of documents per `entity_id`. The agent reads and writes it through server-side tools, so it needs three things: the store attached (`memory_stores=["ws_refund_memory"]`), the tools in `settings.tools` (`retrieve_memory_stores`, `query_memory_store`, `write_memory_store`), and instructions that say when to save and when to query. The call then carries `memory={"entity_id": ...}`; from curl it is `"memory": {"entity_id": "..."}`, from the CLI `--memory '{"entity_id": "..."}'`.

```text
── Step 7 · Memory ────────────────────────────────────
agent    : ws-refund-agent-memory
entity   : customer-user_001-1789512500
turn 1   : Nice to meet you, Jane Okafor, I’ll remember that you prefer store credit over card refunds.
turn 2   : Yes, Jane, I remember that you prefer store credit over card refunds.
trace 2  : 9b16877b2c0de9424a4ed024cf44f584
next     : open trace 2; expect retrieve_memory_stores and query_memory_store spans, then `orq memory-stores list-memories ws_refund_memory`
```

Two things the solution does deliberately. The store key is `ws_refund_memory`: memory store keys must match `^[A-Za-z]([A-Za-z0-9]*([._][A-Za-z0-9]+)*)?$`, so the `ws-` prefix is not allowed. And the memory goes on a copy, `ws-refund-agent-memory`, not on `ws-refund-agent`: once an agent has memory tools, every call without `memory.entity_id` is a `400 Memory entity ID is required`, which would break every other module that invokes `agent/ws-refund-agent`. Check the store: `orq memory-stores list-memories ws_refund_memory`.

### Step 8 · Versions and `@version` routing

`orq.agents.update(agent_key=, ..., version_increment="minor", version_description="...")` publishes a version. Invoke a pinned version with `agent/<key>@<version>`, an environment with `agent/<key>@<environment>`; no suffix means `latest`.

```text
── Step 8 · Versions and @version routing ─────────────
version  : ws-refund-agent already at v1.1.0 (bump skipped, idempotent)
call     : agent/ws-refund-agent@1.0.0        ok, trace 7a78a06c0065a70736d88491695a8904
call     : agent/ws-refund-agent@1.1.0        ok, trace 4ad271bc8ac4a57675fe2ae3d606d04c
call     : agent/ws-refund-agent@latest       ok, trace 72c0cca86acfce6b3ff22f09ee2281c9
call     : agent/ws-refund-agent@production   version @production not found for agent ws-refund-agent
next     : assign the production environment in Agents > ws-refund-agent > Versions, rerun, and @production resolves
```

Environments are assigned in the Studio: **Agents** > `ws-refund-agent` > **Versions** > the version's environment menu > `production`. Do it now and re-run: `@production` resolves. The bump changes only the description, so the agent behaves the same; the solution skips it on re-runs.

### Step 9 · The same from the CLI

Every step above has a CLI twin, all on `orq responses create --model agent/<key>`: `--stream`, `--variables k=v`, `--metadata k=v`, `--identity`, `--thread`, `--previous-response-id`, `--tool-choice`, `--memory`, `--background`, and `orq responses get <id>`. What the CLI adds is the trace search:

```bash
$ orq responses create --model agent/ws-refund-agent --input '"One sentence: what is the refund window?"' -o json | jq '{trace: .telemetry.trace_id, text: .output[0].content[0].text}'
$ orq traces search --from 5m --to now -o json | jq '.data[] | select(.name == "ws-refund-agent") | .trace_id' | head -3
```

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the build-agent skill to create an agent `ws-refund-agent-v2` in path `orq-workshop/workshop` with the same instructions, model and function tools as `ws-refund-agent` (tools by key: `ws-lookup-order`, `ws-get-policy`, `ws-issue-refund`), plus the existing function tool `ws-escalate-to-human`. Add one line to the instructions: above the EUR 500 limit, call `escalate_to_human(order_id, reason)` and give the customer the ticket id. Then invoke it through the Responses API with `model="agent/ws-refund-agent-v2"` and input "refund ord_a6", execute the `function_call` items with `app.refund_agent.tools.dispatch` (answer `escalate_to_human` with a fake ticket id), continue with `previous_response_id` until the agent answers, and show me the trace with `orq traces thread <trace_id>`.

## Proof

![Studio: Agents list showing ws-refund-agent and the variants each module step in this repo creates (approval, delegating, mcp, memory, rag, vulnerable).](assets/studio-agents.png)

## Done when

- [ ] `run.py` completes a refund with `tools=['lookup_order', 'get_policy', 'issue_refund']` and `orq traces thread <last trace>` shows the answer
- [ ] A stream printed its first token before the full answer
- [ ] The step 4 response echoes `variables` and `metadata`, and `orq traces get` shows `identity_id` and `thread_id`
- [ ] Turn 2 answered `89` from `previous_response_id` alone, and `orq responses get` returned the same response
- [ ] `tool_choice="none"` produced a `message` and no `function_call`
- [ ] `orq memory-stores list-memories ws_refund_memory` lists an entity with one document, and turn 2 recalled the name
- [ ] `orq agents retrieve ws-refund-agent -o json | jq .version` is `1.1.0` and `@1.0.0` still answers
- [ ] You can say which output item types your loop must answer and which it must not

## Gotchas

- `orq agents get` does not exist; it is `orq agents retrieve <key>`.
- Each `responses.create` is a new trace, also with `previous_response_id`. Search by agent name, or pass `thread={"id": ...}` to group them in the thread view.
- `tool_approval_required` and `requires_approval` exist on the agent, but through the Responses API they change nothing: function tools always come back to you (you are the approval), and a server-side tool with `requires_approval: true` still ran in our test. See `solution/stretch_factor7.py`.
- The agent's attached knowledge base (`ws-refund-policy`) is never searched in these traces; the agent uses `get_policy`. Module 09 covers why, and what retrieval looks like.
- `orq.agents.responses.create(agent_key=, message=, task_id=)` still works but the SDK marks it deprecated, and the docs now list every `/v2/agents` invoke endpoint (`task`, `stream-task`, `run`) as deprecated. Use `orq.responses.create(model="agent/<key>")`.
- `metadata` values must be strings. `identity` and `thread` are not echoed on the response; look for them on the trace.
- SDK 4.14 rejects the built-in tool names the docs use (`orq:datetime`, `orq:web_search`) client-side; it knows `orq:current_date`, `orq:google_search`, `orq:web_scraper`. Either way, attach built-ins to the agent, a request `tools` array is ignored on `agent/` calls.

## New in orq 4.13

Agents can delegate: an `advisor` tool consults a second model mid-turn and a `sidekick` tool hands off a discrete task, each metered on its own span. Module 15 is that pattern on `ws-refund-agent-delegating`, down to the cost split in the trace. 4.12 added a configurable timeout per agent tool.

## Go further

- Module 15: advisor and sidekick on a copy of this agent, with the nested spans (`advisor` > `chat gpt-5.6-sol`, `sidekick` > `chat gpt-5.4-nano`) and what each costs.
- `solution/stretch_factor7.py`: a human gate in the tool loop plus an `escalate_to_human` tool, on `ws-refund-agent-approval`. Above the limit the agent opens ticket `HR-ord_a6-0001` instead of writing "we will route you".
- Docs: [Run agents](https://docs.orq.ai/docs/ai-studio/ai-engineering/run-agents), [Responses API](https://docs.orq.ai/docs/ai-gateway/features/responses-api), [Memory stores](https://docs.orq.ai/docs/ai-studio/ai-engineering/memory-stores), [Advisor and Sidekick](https://docs.orq.ai/docs/ai-studio/cookbooks/common-architecture/advisor-and-sidekick), [Build agents](https://docs.orq.ai/docs/ai-studio/ai-engineering/build-agents), [Create tools](https://docs.orq.ai/docs/ai-studio/ai-engineering/create-tools), [Create response API](https://docs.orq.ai/reference/responses/create-response).
