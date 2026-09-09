# 08 · Managed agents

!!! abstract "Factor 4: Tools are structured outputs, Factor 6: Launch, pause, resume, Factor 10: Small, focused agents"
    The agent lives in orq. Your code is the tool executor: every `function_call` item comes back to you, you answer it, the conversation resumes server-side. One agent, three tools, eight iterations max.

**Time:** 40 min · **Prereqs:** modules 00 to 02, `make seed` · **You will have:** the refund agent invoked through the Responses API with a local tool loop, streamed, given memory, versioned and pinned by `@version`.

## Why

Modules 01 to 07 kept the agent loop in `app/refund_agent/agent.py`. This module moves the loop to orq: instructions, model, tool schemas, iteration and time limits, knowledge base and memory are one entity with versions. The app shrinks to "execute this tool call and send the result back". That is the split the Responses API is built for, and it is what the Studio, the CLI and the coding-agent skills operate on.

## The one concept to understand first

A managed agent does not run your Python. When it decides to call `lookup_order`, the response comes back `status: completed` with a `function_call` output item and stops. You execute it, then continue the same response chain:

```python
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

Open `modules/08-managed-agents/run.py`. The loop in `run_agent` has two `TODO`s. The solution is in `solution/run.py`.

### Step 1 · Inspect the agent

```bash
$ orq agents retrieve ws-refund-agent --json | jq '{key, version, model: .model.id, settings: {max_iterations: .settings.max_iterations, max_execution_time: .settings.max_execution_time, tool_approval_required: .settings.tool_approval_required, tools: [.settings.tools[] | {action_type, key, requires_approval}]}, knowledge_bases}'
$ uv run python modules/08-managed-agents/run.py
```

Expected output:

```text
[1] ws-refund-agent v1.0.0 model=openai/gpt-4o-mini status=live
    max_iterations=8 max_execution_time=120s tool_approval_required=respect_tool
    tools (as READ): [('function', 'ws-lookup-order', '9MDTGY'), ('function', 'ws-issue-refund', 'K3W9Y6'), ('function', 'ws-get-policy', 'BQHTKW')]
    knowledge_bases=[{'knowledge_id': '01M21E5BPY4XF0RRC7NS0RQ63D'}] memory_stores=[]
    PATCH of the GET body -> ValueError: Could not find discriminator field type in {'id': '01M21ED10ADZ3Z9MEQP...
    write shape: settings.tools = [{'type': 'function', 'key': 'ws-lookup-order'}, ...]
```

Reads and writes have different shapes. A GET returns tools as `{action_type, id, key, requires_approval}`; a create or update wants `{"type": "function", "key": "ws-lookup-order"}`. Inline function schemas are rejected: register the tool once (`orq tools create`), then reference it by key. Open the agent in the Studio (**Agents** > `ws-refund-agent`): the same instructions, the tool list, the limits, and a **Versions** tab.

### Step 2 · Invoke it and execute the tool calls

```text
[2] tools=['lookup_order', 'get_policy', 'issue_refund'] steps=4 4.6s cost=$0.00021
    answer: Your refund for order **ord_a2** for the charging dock has been processed successfully. You will see the amoun
    first trace: 0584a8e4784fadf15530853a4a1be96a   last trace: 34c8d8a2e3182ec593db48a708d95bca
    $ orq traces thread 34c8d8a2e3182ec593db48a708d95bca
```

Four requests, four traces: each Responses call is its own trace with an `agent.response` span and a `chat openai/gpt-4o-mini` span. The last one renders the whole conversation because state is server-side:

```bash
$ orq traces thread 9a4a7e1734b3315950990034ce08ca86
<thread trace="9a4a7e1734b3315950990034ce08ca86" span="07dd005bf712bc75" format="responses" model="gpt-4o-mini" duration_ms="1014" tokens="1199">
<message index="0" role="user">
Refund ord_a2 please, the dock does not fit.
</message>
<message index="1" role="assistant">
I've successfully processed your refund for the charging dock that doesn't fit. You should see the amount of EUR 89.00 returned ...
</message>
</thread>
```

The model sometimes confirms the order first and waits ("Would you like to proceed?"), as the instructions ask. Then the turn ends with two tool calls and no refund. That is correct behaviour, not a bug.

### Step 3 · Stream

`stream=True` returns an event stream. Text arrives as `response.output_text.delta` events; a `function_call` arrives as `response.function_call_arguments.delta` and `.done`.

```text
[3] stream: 21 events, first token at 0.79s, first tokens=['The', ' refund', ' window', ' is', ' ', '30']
    text: The refund window is 30 days from the date of purchase.
```

The CLI does the same: `orq agents stream ws-refund-agent --message '{"role":"user","parts":[{"kind":"text","text":"..."}]}'` (that endpoint is the older A2A shape and prints a deprecation warning from the SDK; prefer `orq responses create --model agent/ws-refund-agent --input '"..."'`).

### Step 4 · Memory

A memory store is an embedding-backed store of documents per `entity_id`. The agent reads and writes it through server-side tools, so it needs three things: the store attached (`memory_stores=["ws_refund_memory"]`), the tools in `settings.tools` (`retrieve_memory_stores`, `query_memory_store`, `write_memory_store`), and instructions that say when to save and when to query. The call then carries `memory={"entity_id": ...}`.

```text
[4] memory entity=customer-user_001-1788903612
    turn 1: Hi Jane Okafor! I've noted your preference for store credit over card refunds. How can I assist you
    turn 2: I remember your name is Jane Okafor, and you prefer store credit over card refunds. How can I assist
    trace 2: 9a58ff54e620c43ded4f8c69007841ae  (spans: retrieve_memory_stores, query_memory_store)
```

Two things the solution does deliberately. The store key is `ws_refund_memory`: memory store keys must match `^[A-Za-z]([A-Za-z0-9]*([._][A-Za-z0-9]+)*)?$`, so the `ws-` prefix is not allowed. And the memory goes on a copy, `ws-refund-agent-memory`, not on `ws-refund-agent`: once an agent has memory tools, every call without `memory.entity_id` is a `400 Memory entity ID is required`, which would break every other module that invokes `agent/ws-refund-agent`. Check the store: `orq memory-stores list-memories ws_refund_memory`.

### Step 5 · Versions and `@version` routing

`orq.agents.update(agent_key=, ..., version_increment="minor", version_description="...")` publishes a version. Invoke a pinned version with `agent/<key>@<version>`, an environment with `agent/<key>@<environment>`; no suffix means `latest`.

```text
[5] bumped ws-refund-agent -> v1.1.0
    agent/ws-refund-agent@1.0.0       ok   trace=a234959c67741a037a37895a3a3bea5e
    agent/ws-refund-agent@1.1.0       ok   trace=320e74c72b3533fcbdfc00c07432f31b
    agent/ws-refund-agent@latest      ok   trace=b13420530ecc6fd573c4f2b4bfb6626c
    agent/ws-refund-agent@production  version @production not found for agent ws-refund-agent
```

Environments are assigned in the Studio: **Agents** > `ws-refund-agent` > **Versions** > the version's environment menu > `production`. Do it now and re-run: `@production` resolves. The bump changes only the description, so the agent behaves the same; the solution skips it on re-runs.

### Step 6 · The same from the CLI

```bash
$ orq responses create --model agent/ws-refund-agent --input '"One sentence: what is the refund window?"' --json | jq '{trace: .telemetry.trace_id, text: .output[0].content[0].text}'
$ orq traces search --from 5m --to now --json | jq '.data[] | select(.name == "ws-refund-agent") | .trace_id' | head -3
```

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the build-agent skill to create an agent `ws-refund-agent-v2` in path `orq-workshop/workshop` with the same instructions, model and function tools as `ws-refund-agent` (tools by key: `ws-lookup-order`, `ws-get-policy`, `ws-issue-refund`), plus the existing function tool `ws-escalate-to-human`. Add one line to the instructions: above the EUR 500 limit, call `escalate_to_human(order_id, reason)` and give the customer the ticket id. Then invoke it through the Responses API with `model="agent/ws-refund-agent-v2"` and input "refund ord_a6", execute the `function_call` items with `app.refund_agent.tools.dispatch` (answer `escalate_to_human` with a fake ticket id), continue with `previous_response_id` until the agent answers, and show me the trace with `orq traces thread <trace_id>`.

## Done when

- [ ] `run.py` completes a refund with `tools=['lookup_order', 'get_policy', 'issue_refund']` and `orq traces thread <last trace>` shows the answer
- [ ] A stream printed its first token before the full answer
- [ ] `orq memory-stores list-memories ws_refund_memory` lists an entity with one document, and turn 2 recalled the name
- [ ] `orq agents retrieve ws-refund-agent --json | jq .version` is `1.1.0` and `@1.0.0` still answers
- [ ] You can say which output item types your loop must answer and which it must not

## Gotchas

- `orq agents get` does not exist; it is `orq agents retrieve <key>`.
- Each `responses.create` is a new trace, also with `previous_response_id`. Search by agent name, or pass `thread={"id": ...}` to group them in the thread view.
- `tool_approval_required` and `requires_approval` exist on the agent, but through the Responses API they change nothing: function tools always come back to you (you are the approval), and a server-side tool with `requires_approval: true` still ran in our test. See `solution/stretch_factor7.py`.
- The agent's attached knowledge base (`ws-refund-policy`) is never searched in these traces; the agent uses `get_policy`. Module 09 covers why, and what retrieval looks like.
- `orq.agents.responses.create(agent_key=, message=, task_id=)` still works but the SDK marks it deprecated. Use `orq.responses.create(model="agent/<key>")`.

## New in orq 4.13

Agents can delegate: an `advisor` tool consults a second model mid-turn and a `sidekick` tool hands off a discrete task, each metered on its own span. `solution/stretch_advisor_sidekick.py` adds both to a copy of the refund agent and prints the nested spans (`advisor` > `chat gpt-4.1`, `sidekick` > `chat gpt-4.1-mini`). 4.12 added a configurable timeout per agent tool.

## Go further

- `solution/stretch_advisor_sidekick.py`: delegation with nested spans on `ws-refund-agent-delegating`.
- `solution/stretch_factor7.py`: a human gate in the tool loop plus an `escalate_to_human` tool, on `ws-refund-agent-approval`. Above the limit the agent opens ticket `HR-ord_a6-0001` instead of writing "we will route you".
- Docs: [Run agents](https://docs.orq.ai/docs/ai-studio/ai-engineering/run-agents), [Responses API](https://docs.orq.ai/docs/ai-gateway/features/responses-api), [Memory stores](https://docs.orq.ai/docs/ai-studio/ai-engineering/memory-stores), [Advisor and Sidekick](https://docs.orq.ai/docs/ai-studio/cookbooks/common-architecture/advisor-and-sidekick).
