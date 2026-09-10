# 02 · Tracing

!!! abstract "Factor 3: Own your context window, and Factor 5: Unify execution and business state"
    The trace is the context window you can read after the fact: every model call, every tool result, in order. Identity, thread and metadata ride on the same request, so who asked, in which conversation, on which plan, is on the trace and not in a side table.

**Time:** 30 min · **Prereqs:** module 01 · **You will have:** traces you can search by thread and customer, one trace that reads `refund_turn -> tool -> llm`, one human annotation on it.

## Why

Module 01 left traces behind without a line of code. This module makes them yours: name them, group them per conversation, attach the customer, then add your own spans so the agent loop is one trace instead of one trace per model call. Every later module (failure analysis, evals, red teaming) starts from these traces.

## The one concept to understand first

Three things decide what a trace looks like, and all three are in your hands:

1. **Request fields.** On `/v3/router/chat/completions`, `name`, `identity`, `thread` and `metadata` are top-level fields of the request body. The OpenAI SDK forwards them through `extra_body`. They become filters in the Studio and in `orq.traces.search` ([request metadata](https://docs.orq.ai/docs/ai-gateway/request-metadata), [thread management](https://docs.orq.ai/docs/ai-gateway/thread-management)).
2. **The W3C `traceparent` header.** When a gateway call carries it, the gateway continues your trace instead of starting its own. `run_turn` adds it from the active `@traced` span (via `orq_ai_sdk.traced.propagation_headers()`).
3. **`@traced` spans.** `@traced(type="agent")` and `@traced(type="tool")` from `orq_ai_sdk.traced` add the spans the gateway cannot see. With `TRACING=otel` the app's `setup_otel()` exports them over OTLP to `https://my.orq.ai/v2/otel`.

```python
body = {"name": "refund-turn", "identity": {"id": "customer-user_001"}, "thread": {"id": thread_id}, "metadata": {"tier": "free"}}
chat("Refund ord_a2 please", extra_body=body)

@traced(type="agent", name="refund_turn")
def refund_turn(text):
    return chat(text)   # run_turn sends traceparent, the gateway nests under this span
```

![Diagram: who produces which span. Your app emits the @traced root span refund_turn and its three tool spans and ships them over OTLP; the gateway emits one chat.openai trace per model call with a span.chat_completion child, nested under the root because run_turn sends the W3C traceparent header; the request body fields name, identity, thread and metadata become filters in the Traces view and the CLI.](assets/span-ownership.png)

## Steps

Open `modules/02-tracing/run.py`. Each step is a function with a `TODO`. The solution is in `solution/run.py`.

### Step 1 · The traces you already have

```bash
$ uv run python modules/02-tracing/run.py
```

Expected output (first block):

```text
[1] zero-code      trace=9d8a4cbd655c96765c984697cd3dc80f tools=['lookup_order', 'get_policy']
    b20be563f59da684df0feaab0a60902b  InvokeEvaluator  ok      1339 ms  $0.000109
    763ddf7b3798d463370571b681ff8fcb  chat.openai      ok       705 ms  $0.000138
    1b2e224f4ddb801e1b90d4b662c0bf42  chat.openai      ok       698 ms  $0.000126
```

Every gateway call is a trace named `chat.openai`. A turn with two tool calls is three traces. The same list from the CLI, and one trace rendered as a conversation:

```bash
$ set -a; source .env; set +a          # the CLI otherwise searches the project of your `orq` session
$ orq traces search --from now-10m --to now --limit 3 --json | jq -c '.data[] | {trace_id, name, status, cost: .cost.total}'
{"trace_id":"61f18a57a68b183f02c0a629de4198ac","name":"chat.openai","status":"ok","cost":0.0001464}
{"trace_id":"cdff0cc2dd384ee7cc1a40204e556bb1","name":"chat.openai","status":"ok","cost":0.00010785}
{"trace_id":"ce398938d1e040e0b31459424df6c996","name":"chat.openai","status":"ok","cost":0.00008835}
$ orq traces thread 1535afaef44e7ecd26efa9fce587c434
```

```text
<thread trace="1535afaef44e7ecd26efa9fce587c434" span="6a659fe8b9570831" format="chat_completions" model="gpt-4o-mini" duration_ms="759" tokens="1266">

<message index="0" role="assistant">
To proceed with a refund for damage in transit, I will need a tracking reference that confirms the damage occurred. Please provide that information, and then we can move forward.
</message>

</thread>
```

### Step 2 · Name, identity, thread, metadata

Fill `step_2_thread`: put `name`, `identity`, `thread` and `metadata` in `extra_body`, call `chat()` twice with the same thread id and the first turn's `messages` as history, then search by `thread_id`.

```text
[2] thread         id=ws-thread-1a46c21f
    turn 1 trace=0684d0ddc0ac3c84831e9aedd9b58733 tools=['lookup_order', 'get_policy']
    turn 2 trace=1535afaef44e7ecd26efa9fce587c434 tools=[]
    search thread_id=ws-thread-1a46c21f -> 4 traces: ['1535afaef44e7ecd26efa9fce587c434', '0684d0ddc0ac3c84831e9aedd9b58733', '5f373aab0c4575c348bd90567f61a57b', 'bacac7c2558bfdf35ee53d0c574e44cf']
    turn 2: name=refund-turn identity_id=customer-user_001 thread_id=ws-thread-1a46c21f
```

Four traces, one conversation: turn 1 made three model calls, turn 2 made one. In the Studio, open **Traces**, filter on Thread ID, and the four line up. The same filters work on `identity_id`, `metadata.tier` and `name`:

```bash
$ orq traces search --from now-15m --to now --filters '[{"field":"thread_id","op":"eq","values":["ws-thread-1a46c21f"]}]' --json | jq -c '{rows: .meta.row_count, traces: [.data[].trace_id]}'
{"rows":4,"traces":["1535afaef44e7ecd26efa9fce587c434","0684d0ddc0ac3c84831e9aedd9b58733","5f373aab0c4575c348bd90567f61a57b","bacac7c2558bfdf35ee53d0c574e44cf"]}
```

### Step 3 · One trace per turn with `@traced`

Set `TRACING=otel` in `.env`, or call `tracing.setup_otel(force=True)` as the solution does (a shell export loses to `.env`). Fill `step_3_otel`: decorate `refund_turn` with `@traced(type="agent", name="refund_turn")` and wrap each tool dispatch in `@traced(type="tool", name=name)`. `run_turn` already sends the `traceparent` of the active span. `app/` does not change: the solution replaces `agent.dispatch` at runtime.

```text
[3] otel + @traced trace=6a8b286306a224a4a00683cafcf8312d tools=['lookup_order', 'get_policy', 'issue_refund']
    root    trace                  refund_turn                  unset                        8d7979f6a9e57993
      child trace                  chat.openai                  ok    gpt-4o-mini            d31a6a8b48b98c31
      child span.chat_completion   chat gpt-4o-mini             ok    gpt-4o-mini            1d8590e102fa4e3d
      child span.agent_tool_execution lookup_order                 ok                           327fc73e434fe3bc
      child trace                  chat.openai                  ok    gpt-4o-mini            08e6c0c836050cc9
      child span.chat_completion   chat gpt-4o-mini             ok    gpt-4o-mini            20107820e1cdf85c
      child span.agent_tool_execution get_policy                   ok                           71ae33e0b2f96746
      child trace                  chat.openai                  ok    gpt-4o-mini            28fb460abc7b5e37
      child span.chat_completion   chat gpt-4o-mini             ok    gpt-4o-mini            92c88b240430a5a6
      child span.agent_tool_execution issue_refund                 ok                           13ce52648ae1f8c1
      child trace                  chat.openai                  ok    gpt-4o-mini            5dc629772dd0736f
      child span.chat_completion   chat gpt-4o-mini             ok    gpt-4o-mini            d6d1e288da3d8499
```

One root `refund_turn` span, four gateway calls nested under it, three tool spans between them in the order the model called them. `tracing.flush()` before exit matters: the batch exporter ships on a timer and a short script exits first.

### Step 4 · Annotate the answer

Fill `step_4_annotation` with `annotations=[{"key": "rating", "value": "good"}]` on the last `span.chat_completion`.

```text
[4] annotation     rating=good on span d6d1e288da3d8499 of trace 6a8b286306a224a4a00683cafcf8312d
```

A key has to exist as an annotation definition first. This workspace has `rating`; any other key returns:

```text
Status 404. Body: {"code":"deployment_not_found","message":"The human review with key \"ws-does-not-exist\" for workspace 624ccbbd-... was not found.","category":"not_found",...}
```

If you get that for `rating`, create it in the Studio: **Optimization > Annotations > Create**, key `rating`, type categorical with values `good` and `bad`, then rerun. Annotations are queryable later (module 04 uses them as labels).

### Step 5 · Stretch: a framework does this for you

```bash
$ uv run python modules/02-tracing/solution/stretch_langgraph.py
```

```text
answer : I've processed your refund for order ord_a2, as the dock does not fit your laptop. You will see the amount of EUR 89.00
steps  : ['human', 'ai', 'tool', 'ai', 'tool', 'ai', 'tool', 'ai']
trace  : 01a082fcf4ca7cb1ba6b49f581e2d0b5  spans=31  {'trace': 1, 'span.agent': 7, 'span.chain': 16, 'span.chat_completion': 4, 'span.tool': 3}
```

One `setup()` from `orq_ai_sdk.langchain` before the graph is built, and every node, tool and model call is a span; the Studio draws the graph next to the trace. Strands agents get the same treatment through OpenTelemetry: [docs.orq.ai/docs/ai-studio/integrations/frameworks/aws-strands](https://docs.orq.ai/docs/ai-studio/integrations/frameworks/aws-strands).

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the `setup-observability` skill against this repository. Do not change anything: report what the skill would change, which integration mode it picks for this app, which spans it would add with `@traced` and with which types, and which of its recommendations the module already implements. Then use the orq MCP tools to fetch the spans of the most recent trace named `refund_turn` and tell me the order of tool spans and model calls inside it.

## Done when

- [ ] `orq traces search` filtered on your thread id returns every model call of the conversation
- [ ] A trace with a root span named `refund_turn` and three `span.agent_tool_execution` children exists
- [ ] That trace carries a `rating` annotation (open it in the Studio, Annotations panel)
- [ ] `git status` shows changes under `modules/02-tracing/` and `.env` only

## Gotchas

- `.env` beats the shell: `TRACING=otel uv run ...` still reads `TRACING=gateway` from `.env`. Edit `.env` or do what the solution does.
- On chat completions, `identity`, `thread` and `metadata` worked as top-level body fields here. Nested under `orq` (the shape the request-metadata docs describe for this endpoint) they were silently ignored: `identity_id` and `thread_id` stayed empty.
- The SDK's automatic `traceparent` injection (a patch on `httpx.Client.send`) did not reach the OpenAI client (openai 3.9, httpx 0.28), so `run_turn` merges `propagation_headers()` into the request headers itself. If you call the gateway from your own code inside a `@traced` function, pass `extra_headers=propagation_headers()`.
- `orq traces search` needs `--from` and `--to`; relative values are `now-10m` and `now`. Without `ORQ_API_KEY` in the shell the CLI searches the project of your `orq` session, which is not necessarily this one.
- `orq.traces.get` and `get_span` return the metadata block empty in SDK 4.14.14. `orq request GET /v3/traces/<id> --json | jq .body.trace.attributes.metadata` shows it.
- `list_spans` reports the `@traced` root as type `trace` and tools as `span.agent_tool_execution`; the Studio reads the `agent` / `tool` type from the span attributes.

## New in orq 4.14

Every trace span now shows guardrail and evaluator indicators, the Traces view has a time-range selector and search by id, and (since 4.11) Human Review is called Annotations with queues and the API used in step 4.

## Go further

Filter by `metadata.tier` in the Studio and save it as a view: that is the "free tier customers" slice module 05 puts a budget on. The `orq traces thread` command accepts `--slice -1` to print only the last message, which is what `orq traces insights` summarises across a time range.

Docs: [Traces](https://docs.orq.ai/docs/ai-studio/observability/traces), [Observability quickstart (OTLP)](https://docs.orq.ai/docs/ai-studio/observability/quickstart), [Span attributes](https://docs.orq.ai/docs/ai-studio/observability/span-attributes), [Request metadata](https://docs.orq.ai/docs/ai-gateway/request-metadata), [Thread management](https://docs.orq.ai/docs/ai-gateway/thread-management), [Identities](https://docs.orq.ai/docs/ai-studio/observability/identities), [Annotations](https://docs.orq.ai/docs/ai-studio/observability/annotations), [LangGraph integration](https://docs.orq.ai/docs/ai-studio/integrations/frameworks/langgraph).
