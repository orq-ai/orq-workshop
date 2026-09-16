# Build your own agent

Most teams already have an agent framework, or a loop they wrote themselves, and no appetite for rewriting either. The question is not *should we adopt orq's agent* — it is *can we keep our architecture and still get prompts, routing, tracing and tool tracing from orq*.

The answer is yes, and this page is the proof: the same refund turn, run three ways, against the same instructions, the same three tools and the same gateway. What changes is **who owns the agentic loop**.

## The same turn, three ways

Run it yourself — `uv run python examples/own-your-agent.py`, after `make seed`:

```text
── Leg 1 · Raw orq Python SDK ─────────────────────────
question : Refund ord_a2 please, the dock does not fit my laptop.
answer   : Your refund of **€89** for order ord_a2 has been issued to the original payment method. …
tools    : lookup_order → get_policy → issue_refund
trace    : c8ad8bc87a4e5d1f9b7f74a81832962a
took     : 6.2s
── Leg 2 · LangGraph ──────────────────────────────────
steps    : human → ai → tool → ai → tool → ai → tool → ai
trace    : 01a0a7f92af27b93b07e7c8ff17e85bc
took     : 4.3s
── Leg 3 · Managed agent ──────────────────────────────
tools    : lookup_order → get_policy → issue_refund
traces   : 4 responses, last 4c1d29e50d6eae0d69585660a929d97a
took     : 5.8s
```

Three trace ids, one question. Open them side by side in the Studio: same tools called in the same order, same refund, three different shapes of trace.

| | Raw orq SDK | LangGraph | Managed agent |
|---|---|---|---|
| Who owns the loop | you | the framework | orq |
| Where it lives | `app/refund_agent/agent.py` | `create_react_agent` | `ws-refund-agent`, in orq |
| Protocol | Responses API | chat-completions | `model="agent/<key>"` |
| Tools execute in | your process | your process | your process, or orq's |
| Tracing setup | none — the gateway traces it | one line | none |
| Trace id comes from | the response header | a lookup by run name | the response |
| Changing the prompt | edit a file, redeploy | edit a file, redeploy | edit in orq, no deploy |

## The four connection points

Everything the client of this workshop asked for maps to one of four seams. None requires giving up your agent framework.

**Prompts.** Today all three legs read `INSTRUCTIONS` from a repo file — which is why that row of the table is the same in all three columns and answers nothing yet. Moving it into an orq Deployment is what makes the third column different: a prompt you can version and change without shipping code. That step is not in the workshop yet.

**Routing.** One base URL. `https://my.orq.ai/v3/router` is a drop-in for the OpenAI endpoint, which is why leg 2 needed no orq-specific code at all — `ChatOpenAI(base_url=...)` and the call is routed, budgeted, cached and traced. Fallbacks, smart routing and routing rules apply to all three legs equally ([module 01](modules/01.md), [module 03](modules/03.md)).

**Tracing.** Three methods, in ascending order of effort:

| Method | Setup | Use it when |
|---|---|---|
| Gateway traces | none — every call through the router is a trace | always; it is the floor |
| Framework callback | `orq_ai_sdk.langchain.setup()`, one line | you use LangChain or LangGraph |
| OpenTelemetry + `@traced` | `TRACING=otel`, decorators, `traceparent` | you already run OTEL, or want custom spans |

orq's own guidance is to *pick the callback handler unless you have a specific reason not to*, and reach for OpenTelemetry when you have existing OTEL infrastructure or need control over span attributes. [Module 02](modules/02.md) runs all three.

**Tool tracing.** In legs 1 and 2 the tools run in your process, so what the trace shows is what you instrument: the gateway sees the model calls, and a tool span appears only if the framework emits one (LangGraph does) or you decorate the dispatch yourself (module 02, step 3). A managed agent is the exception — orq executes server-side tools and the retrieval or delegation lands in the trace without you doing anything.

## Two things the comparison exposes

**Leg 2 speaks a different protocol, and it shows.** LangGraph goes through `/chat/completions`, where GPT-5.x rejects tool definitions unless `reasoning_effort="none"` — a real 400, and one this repo already documents in [troubleshooting](reference/troubleshooting.md). Legs 1 and 3 use the Responses API, where the question never arises. So the three traces are comparable in content but not span-for-span identical.

**Instrumenting nothing has a price.** Legs 1 and 3 get a trace id back on the response itself. Leg 2 never touches the graph, so it has to name the run and look the trace up afterwards, once the gateway has indexed it. Zero-touch instrumentation costs you the immediate handle.

## Choosing

- **Your own loop** when the control flow is the product: explicit steps, your own retries, your own state. You keep every seam and give up nothing but convenience.
- **A framework** when the graph is worth having and you want the ecosystem. One line of setup and orq observes it.
- **A managed agent** when the agent is configuration rather than code, and you want prompts, tools and versions changeable without a deploy — at the cost of the loop running somewhere you cannot step through.

The three are not exclusive. A managed agent can call tools your service exposes over MCP ([module 10](modules/10.md)); a framework agent can read a knowledge base orq hosts ([module 09](modules/09.md)); all three land in the same traces, the same budgets and the same evaluations.

## Related

- [`examples/own-your-agent.py`](https://github.com/orq-ai/orq-workshop/blob/main/examples/own-your-agent.py) — the script behind this page
- [Module 08 · Managed agents](modules/08.md) · [Module 02 · Tracing](modules/02.md) · [How retrieval works](reference/rag.md)
- [orq.ai · Tracing LangGraph](https://orq.ai/blog/tracing-langgraph-orq-ai) · [Building a LangGraph agent on orq.ai](https://orq.ai/blog/langgraph-agent-orq-ai)
