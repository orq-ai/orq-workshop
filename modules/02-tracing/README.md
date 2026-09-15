# 02 · Tracing

!!! abstract "Factor 3: Own your context window, and Factor 5: Unify execution and business state"
    The trace is the context window you can read after the fact: every model call, every tool result, in order. Identity, thread and metadata ride on the same request, so who asked, in which conversation, on which plan, is on the trace and not in a side table.

| | |
|---|---|
| **Time** | 30 min |
| **Prerequisites** | module 01 |
| **You will have** | traces you can search by thread and customer, one trace that reads `refund_turn -> tool -> llm`, one human annotation on it. |

## Why

Module 01 left traces behind without a line of code. This module makes them yours: name them, group them per conversation, attach the customer, then add your own spans so the agent loop is one trace instead of one trace per model call. Every later module (failure analysis, evals, red teaming) starts from these traces.

## The one concept to understand first

Three things decide what a trace looks like, and all three are in your hands:

1. **Request fields.** On `/v3/router/responses` (and on `/chat/completions`), `name`, `identity`, `thread` and `metadata` are top-level fields of the request body. The OpenAI SDK forwards them through `extra_body`. They become filters in the Studio and in `orq.traces.search` ([request metadata](https://docs.orq.ai/docs/ai-gateway/request-metadata), [thread management](https://docs.orq.ai/docs/ai-gateway/thread-management)).
2. **The W3C `traceparent` header.** When a gateway call carries it, the gateway continues your trace instead of starting its own. `run_turn` adds it from the active `@traced` span (via `orq_ai_sdk.traced.propagation_headers()`).
3. **`@traced` spans.** `@traced(type="agent")` and `@traced(type="tool")` from `orq_ai_sdk.traced` add the spans the gateway cannot see. With `TRACING=otel` the app's `setup_otel()` exports them over OTLP to `https://my.orq.ai/v2/otel`.

```python
body = {"name": "refund-turn", "identity": {"id": "customer-user_001"}, "thread": {"id": thread_id}, "metadata": {"tier": "free"}}
chat("Refund ord_a2 please", extra_body=body)

@traced(type="agent", name="refund_turn")
def refund_turn(text):
    return chat(text)   # run_turn sends traceparent, the gateway nests under this span
```

![Diagram: who produces which span. Your app emits the @traced root span refund_turn and its three tool spans and ships them over OTLP; the gateway emits one responses.openai trace per model call with a span.responses child, nested under the root because run_turn sends the W3C traceparent header; the request body fields name, identity, thread and metadata become filters in the Traces view and the CLI.](assets/span-ownership.png)

## Steps

Open `modules/02-tracing/run.py`. Each step is a function with a `TODO`. The solution is in `solution/run.py`.

### Step 1 · The traces you already have

```bash
$ uv run python modules/02-tracing/run.py
```

Expected output (first block):

```text
── Step 1 · The traces you already have ───────────────
question : Refund ord_a2 please, the dock does not fit my laptop.
answer   : Your refund of **€89.00** for order **ord_a2** has been issued to the original payment method. Pleas…
tools    : lookup_order → get_policy → issue_refund
trace    : 610d07561cb9a9ef8668fc0fc6805783
recent   : the last 5 traces of the workspace, one per gateway call
    7cd1b5c0c1566726a56e240f9aa5ab94  responses.openai ok      2134 ms  $0.000265
    0e4651ec7e1f45fe80b7cf8b6c326b77  responses.openai ok      1379 ms  $0.000201
    3d96282c5b60dd9ce87efcebc5473351  responses.openai ok      1767 ms  $0.000212
    6cdc5dd1b1d4e30375cd0a4e620dd8ec  responses.openai ok      5509 ms  $0.022867
    9f530706a4d69dd3eb187aabef9c88ed  responses.openai ok      3396 ms  $0.006166
cli      : orq traces search --from now-10m --to now -o json | jq '.data[] | {trace_id, name}'
next     : open https://my.orq.ai/traces; every gateway call is its own trace, named after the endpoint
```

Every gateway call is a trace named after its endpoint, `responses.openai` here (`chat.openai` for chat completions, `responses.<workspace>@orq` for a smart router; rows from other modules, such as 04's `pii *` plugin spans, show up too if they ran recently). A turn with two tool calls is three traces. The same list from the CLI, and one trace rendered as a conversation:

```console
$ set -a; source .env; set +a          # the CLI otherwise searches the project of your `orq` session
$ orq traces search --from now-10m --to now --limit 3 -o json | jq -c '.data[] | {trace_id, name, status, cost: .cost.total}'
{"trace_id":"e4119747783704db32ff153043c1fa9a","name":"responses.openai","status":"ok","cost":0.0002204}
{"trace_id":"24db29ca280446773e74878862b7391d","name":"responses.openai","status":"ok","cost":0.0002044}
{"trace_id":"b56aa7c55447d568b8a099e81ad7b313","name":"responses.openai","status":"ok","cost":0.00025865}
$ orq traces thread 6d3815f83d19c502ea7bef614d67bc8a
```

```text
<thread trace="6d3815f83d19c502ea7bef614d67bc8a" span="14b9946e7718e1d7" format="responses" model="gpt-5.6-luna" duration_ms="1530" tokens="1485">

<message index="0" role="user">
It was damaged in transit. Please refund it.
</message>

<message index="1" role="assistant">
[content unavailable: 2 items]
</message>

</thread>
```

`[content unavailable: 2 items]` is the CLI, not the trace: orq-cli 8.6 renders chat-completions transcripts and shows Responses output items (a reasoning item plus the message) as unavailable, in every output format. The Studio's thread view renders them. Chat-completions traces render in full, as module 04's captures show.

### Step 2 · Name, identity, thread, metadata

Fill `step_2_thread`: put `name`, `identity`, `thread` and `metadata` in `extra_body`, call `chat()` twice with the same thread id and the first turn's `messages` as history, then search by `thread_id`.

```text
── Step 2 · Name, identity, thread, metadata ──────────
thread   : ws-thread-21c5900e
turn 1   : 5824e4d8a05994578ae60bc187cb42ac  tools lookup_order → get_policy → get_policy
turn 2   : 8d56a5496ab66fa63a806ded661c989c  tools (none)
search   : thread_id=ws-thread-21c5900e → 4 traces: 8d56a5496ab66fa63a806ded661c989c, 5824e4d8a05994578ae60bc187cb42ac, fa4160a67177e03c1dbe2367b5954aff, 9ff5f82d43e0d356539ef797775136d8
fields   : name=refund-turn identity_id=customer-user_001 thread_id=ws-thread-21c5900e
cli      : orq traces thread 8d56a5496ab66fa63a806ded661c989c
next     : in https://my.orq.ai/traces filter on Thread ID ws-thread-21c5900e; every model call of the conversation lines up
```

Four traces, one conversation: turn 1 made three model calls, turn 2 made one. In the Studio, open **Traces**, filter on Thread ID, and the four line up. The same filters work on `identity_id`, `metadata.tier` and `name`:

```console
$ orq traces search --from now-15m --to now --filters '[{"field":"thread_id","op":"eq","values":["ws-thread-9a2d79c4"]}]' -o json | jq -c '{rows: .meta.row_count, traces: [.data[].trace_id]}'
{"rows":4,"traces":["6d3815f83d19c502ea7bef614d67bc8a","14e3eaa42eaf74afb9501aa0817395b5","b86261f809268f38f2a40e49323e5b34","a6f1c0edd571fd176540dc91d7555225"]}
```

### Step 3 · One trace per turn with `@traced`

Set `TRACING=otel` in `.env`, or call `tracing.setup_otel(force=True)` as the solution does (a shell export loses to `.env`). Fill `step_3_otel`: decorate `refund_turn` with `@traced(type="agent", name="refund_turn")` and wrap each tool dispatch in `@traced(type="tool", name=name)`. `run_turn` already sends the `traceparent` of the active span. `app/` does not change: the solution replaces `agent.dispatch` at runtime.

```text
── Step 3 · One trace per turn with @traced ───────────
question : Refund ord_a2 please, the dock does not fit my laptop.
answer   : Your refund of **€89** for order **ord_a2** has been issued to the original payment method. It shoul…
tools    : lookup_order → get_policy → issue_refund
trace    : cb2289e8eae4e587f8bba591734cc831
spans    : oldest first
    root    trace                  refund_turn                  unset                        d712fd0358d4ce02
      child trace                  responses.openai             ok    gpt-5.6-luna           62e90468d43efc07
      child span.responses         chat openai/gpt-5.6-luna     ok    gpt-5.6-luna           2b324819ba24c84a
      child span.agent_tool_execution lookup_order                 ok                           fdafc7009ecb1664
      child trace                  responses.openai             ok    gpt-5.6-luna           b9fa333d5c611a13
      child span.responses         chat openai/gpt-5.6-luna     ok    gpt-5.6-luna           882e2e37d59f5692
      child span.agent_tool_execution get_policy                   ok                           2970e7a2aecf9061
      child trace                  responses.openai             ok    gpt-5.6-luna           3fefa9f4b3358cb6
      child span.responses         chat openai/gpt-5.6-luna     ok    gpt-5.6-luna           78248a60c1d527b8
      child span.agent_tool_execution issue_refund                 ok                           ec74c3b36a223add
      child trace                  responses.openai             ok    gpt-5.6-luna           05f820afc5dc467f
      child span.responses         chat openai/gpt-5.6-luna     ok    gpt-5.6-luna           274c568b4fffdfc5
next     : open the trace in https://my.orq.ai/traces; one root refund_turn, tool spans between the model calls
```

One root `refund_turn` span, four gateway calls nested under it, three tool spans between them in the order the model called them. `tracing.flush()` before exit matters: the batch exporter ships on a timer and a short script exits first.

### Step 4 · Annotate the answer

Fill `step_4_annotation` with `annotations=[{"key": "rating", "value": "good"}]` on the last `span.responses`.

```text
── Step 4 · Annotate the answer ───────────────────────
key      : rating=good
span     : 274c568b4fffdfc5 of trace cb2289e8eae4e587f8bba591734cc831
verdict  : written
next     : open the trace in https://my.orq.ai/traces, Annotations panel; module 17 reads these back as labels
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
── Step 4 · Build the graph and run one turn ──────────
question : Refund ord_a2 please, the dock does not fit my laptop.
answer   : Your refund of €89.00 for order ord_a2 has been issued to the original payment method. It should arr…
steps    : human → ai → tool → ai → tool → ai → tool → ai
next     : the trace is named refund_langgraph; step 5 searches it by that name
── Step 5 · Read the trace back ───────────────────────
trace    : 01a0a736c57f7532a2fb8bc28e42652f
spans    : 31
kinds    : trace 1, span.agent 7, span.chain 16, span.chat_completion 4, span.tool 3
next     : open https://my.orq.ai/traces and search the trace id; the graph panel shows agent → tools → agent
```

One `setup()` from `orq_ai_sdk.langchain` before the graph is built, and every node, tool and model call is a span; the Studio draws the graph next to the trace. Strands agents get the same treatment through OpenTelemetry: [docs.orq.ai/docs/ai-studio/integrations/frameworks/aws-strands](https://docs.orq.ai/docs/ai-studio/integrations/frameworks/aws-strands).

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the `setup-observability` skill against this repository. Do not change anything: report what the skill would change, which integration mode it picks for this app, which spans it would add with `@traced` and with which types, and which of its recommendations the module already implements. Then use the orq MCP tools to fetch the spans of the most recent trace named `refund_turn` and tell me the order of tool spans and model calls inside it.

## Proof

![Studio: Traces list for the orq-workshop project, showing ws-refund-agent runs with duration, tokens and cost per request.](assets/studio-traces.png)

## Done when

- [ ] `orq traces search` filtered on your thread id returns every model call of the conversation
- [ ] A trace with a root span named `refund_turn` and three `span.agent_tool_execution` children exists
- [ ] That trace carries a `rating` annotation (open it in the Studio, Annotations panel)
- [ ] `git status` shows changes under `modules/02-tracing/` and `.env` only

## Gotchas

- `.env` beats the shell: `TRACING=otel uv run ...` still reads `TRACING=gateway` from `.env`. Edit `.env` or do what the solution does.
- On both router endpoints, `identity`, `thread` and `metadata` worked as top-level body fields here. Nested under `orq` (the shape the request-metadata docs describe for this endpoint) they were silently ignored: `identity_id` and `thread_id` stayed empty.
- The SDK's automatic `traceparent` injection (a patch on `httpx.Client.send`) did not reach the OpenAI client (openai 3.9, httpx 0.28), so `run_turn` merges `propagation_headers()` into the request headers itself. If you call the gateway from your own code inside a `@traced` function, pass `extra_headers=propagation_headers()`.
- `orq traces search` needs `--from` and `--to`; relative values are `now-10m` and `now`. Without `ORQ_API_KEY` in the shell the CLI searches the project of your `orq` session, which is not necessarily this one.
- `orq.traces.get` and `get_span` return the metadata block empty in SDK 4.14.14. `orq request GET /v3/traces/<id> -o json | jq .body.trace.attributes.metadata` shows it.
- `list_spans` reports the `@traced` root as type `trace` and tools as `span.agent_tool_execution`; the Studio reads the `agent` / `tool` type from the span attributes. Gateway model spans are `span.responses` on the Responses endpoint and `span.chat_completion` on chat completions; filter on both.
- `orq traces thread` prints `[content unavailable: N items]` for a Responses-format assistant turn (orq-cli 8.6). Use the Studio thread view, or `orq traces get-span` on the span for the raw output.

## New in orq 4.14

Every trace span now shows guardrail and evaluator indicators, the Traces view has a time-range selector and search by id, and (since 4.11) Human Review is called Annotations with queues and the API used in step 4.

## Go further

Filter by `metadata.tier` in the Studio and save it as a view: that is the "free tier customers" slice module 05 puts a budget on. The `orq traces thread` command accepts `--slice -1` to print only the last message, which is what `orq traces insights` summarises across a time range.

Docs: [Traces](https://docs.orq.ai/docs/ai-studio/observability/traces), [Observability quickstart (OTLP)](https://docs.orq.ai/docs/ai-studio/observability/quickstart), [Span attributes](https://docs.orq.ai/docs/ai-studio/observability/span-attributes), [Request metadata](https://docs.orq.ai/docs/ai-gateway/request-metadata), [Thread management](https://docs.orq.ai/docs/ai-gateway/thread-management), [Identities](https://docs.orq.ai/docs/ai-studio/observability/identities), [Annotations](https://docs.orq.ai/docs/ai-studio/observability/annotations), [LangGraph integration](https://docs.orq.ai/docs/ai-studio/integrations/frameworks/langgraph).
