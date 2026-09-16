# Build your own agent

Most teams already have an agent framework, or a loop they wrote themselves, and no appetite for rewriting either. The question is not *should we adopt orq's agent*. It is *can we keep our architecture and still get prompts, routing, tracing and tool tracing from orq*.

The answer is yes, and this page is the proof: the same refund turn, run three ways, against the same instructions, the same three tools and the same gateway. What changes is **who owns the agentic loop**.

## The same turn, three ways

One question, one set of instructions, one set of three tools, one gateway. Only the owner of the loop changes. Run it yourself with `uv run python examples/own-your-agent.py`, after `make seed`.

### 1 · Your loop — the raw orq SDK

`chat()` is the workshop's own agent: an explicit tool-calling loop over the Responses API, in `app/refund_agent/agent.py`, and you can read all of it.

```python
from app.refund_agent.agent import chat

own = chat(QUESTION)

own.tool_calls   # ['lookup_order', 'get_policy', 'issue_refund']
own.trace_id     # comes back on the response itself
```

Nothing here is orq-specific except the base URL. That is the point: the gateway is a drop-in for the OpenAI endpoint, so a team keeps its own architecture and still gets routing, budgets and traces.

![Diagram: your own loop calling the orq gateway. Your process holds your code, the tool-calling loop you wrote, and the three tools. The loop calls the orq AI Gateway over the Responses API, the gateway calls the model, and a trace id comes back on the response itself.](assets/diagrams/own-agent-leg1.png)

### 2 · A framework — LangGraph runs the loop

One line installs a global LangChain callback, and every node, tool and model call becomes a span. The graph itself is never modified.

```python
from orq_ai_sdk.langchain import setup as orq_langchain_setup
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

orq_langchain_setup(api_key=settings.api_key, api_url=settings.base_url)

graph = create_react_agent(
    ChatOpenAI(
        model=settings.model,
        base_url=settings.router_url,   # the gateway, as a drop-in OpenAI endpoint
        api_key=settings.api_key,
        reasoning_effort="none",        # GPT-5.x rejects tools on /chat/completions without it
    ),
    [lookup_order_tool, get_policy_tool, issue_refund_tool],
    prompt=INSTRUCTIONS,
)

result = graph.invoke(
    {"messages": [{"role": "user", "content": QUESTION}]},
    config={"run_name": GRAPH_TRACE_NAME},   # name it, so the trace can be found afterwards
)
```

Two details this leg pays for, both visible in the output below: it speaks **chat-completions** rather than the Responses API, and because nothing touches the graph there is no trace id on the result — the run has to be named and looked up once the gateway has indexed it.

![Diagram: a LangGraph agent traced through the orq gateway. Your process holds the graph, the loop the framework runs, and the three tools. The graph calls the orq AI Gateway over the chat-completions endpoint and the gateway calls the model. A one-line callback ships spans in the background, so the trace is found afterwards by run name rather than arriving on the response.](assets/diagrams/own-agent-leg2.png)

### 3 · A managed agent — orq runs the loop

The agent is configuration in orq, not code here: instructions, model and tool schemas live server-side. Your code posts the question and answers the `function_call` items it gets back.

```python
response = orq.responses.create(
    model=f"agent/{AGENT_KEY}", input=QUESTION
).model_dump(by_alias=True)

for _ in range(MAX_STEPS):
    # tools orq already ran server-side arrive done - never execute those locally
    done_by_server = {
        item.get("call_id")
        for item in response["output"]
        if item["type"].startswith("orq:")
    }
    pending = [
        item for item in response["output"]
        if item["type"] == "function_call" and item["call_id"] not in done_by_server
    ]
    if not pending:
        break

    outputs = []
    for call in pending:
        result = dispatch(store, call["name"], json.loads(call["arguments"] or "{}"))
        outputs.append({
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps(result),
        })

    response = orq.responses.create(
        model=f"agent/{AGENT_KEY}",
        previous_response_id=response["id"],   # orq keeps the transcript, you keep the pointer
        input=outputs,
    ).model_dump(by_alias=True)
```

![Diagram: a managed agent whose loop runs server-side. Your process posts a question to the agent and the loop runs inside orq, where instructions, model and tool schemas are configuration rather than code. The agent sends function_call items back to your process, which runs the tools locally and returns the results, while orq calls the model itself.](assets/diagrams/own-agent-leg3.png)

The boundary is the whole story: in legs 1 and 2 the loop sits on your side of it, here it sits on orq's. The tools do not move — they still run in your process either way.

### All three, one run

They live in one script on purpose: same `QUESTION` constant, same process, so the comparison is a fact rather than a convention.

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
| Tracing setup | none (the gateway traces it) | one line | none |
| Trace id comes from | the response header | a lookup by run name | the response |
| Changing the prompt | edit a file, redeploy | edit a file, redeploy | edit in orq, no deploy |

### 4 · A harness runs the loop — a sketch

!!! note "Not built in this workshop"
    The three legs above run. This fourth shape does not — it is drawn here because teams keep asking for it, and because it is the one case where you own neither the loop nor the agent.

There is a fourth owner the comparison misses: a **coding-agent harness**. `orq launch pi` (or `claude`, `codex`, `opencode`) starts an agent you did not write and orq does not host, running on your machine against your repo — and every model call still goes through the gateway.

![Diagram: a coding-agent harness routed through orq. On your machine a harness such as pi, Claude Code or Codex runs the loop against your repo and local tools like bash and edit. Every model call goes to the orq AI Gateway so the work is traced and budgeted, and the orq MCP tools and skills, installed by orq connect, reach the harness over MCP.](assets/diagrams/own-agent-leg4.png)

What orq supplies here is not the loop and not the agent — it is the four seams underneath one: the **model** (routed, traced, budgeted like any other call), the **tools** (the orq MCP server), the **skills** that teach it your platform workflows, and the **spend controls** that apply because the traffic is ordinary gateway traffic.

That makes it the strongest version of this page's argument. You can bring a loop you wrote, a loop a framework wrote, a loop orq runs, or a loop a vendor shipped in a binary — and the seams do not change. [Module 13](modules/13.md) wires this one up for real.

## The four connection points

Everything the client of this workshop asked for maps to one of four seams. None requires giving up your agent framework.

**Prompts.** Today all three legs read `INSTRUCTIONS` from a repo file, which is why that row of the table is the same in all three columns and answers nothing yet. Moving it into an orq Deployment is what makes the third column different: a prompt you can version and change without shipping code. That step is not in the workshop yet.

**Routing.** One base URL. `https://my.orq.ai/v3/router` is a drop-in for the OpenAI endpoint, which is why leg 2 needed no orq-specific code at all: `ChatOpenAI(base_url=...)` and the call is routed, budgeted, cached and traced. Fallbacks, smart routing and routing rules apply to all three legs equally ([module 01](modules/01.md), [module 03](modules/03.md)).

**Tracing.** Three methods, in ascending order of effort:

| Method | Setup | Use it when |
|---|---|---|
| Gateway traces | none (every call through the router is a trace) | always; it is the floor |
| Framework callback | `orq_ai_sdk.langchain.setup()`, one line | you use LangChain or LangGraph |
| OpenTelemetry + `@traced` | `TRACING=otel`, decorators, `traceparent` | you already run OTEL, or want custom spans |

orq's own guidance is to *pick the callback handler unless you have a specific reason not to*, and reach for OpenTelemetry when you have existing OTEL infrastructure or need control over span attributes. [Module 02](modules/02.md) runs all three.

**Tool tracing.** In legs 1 and 2 the tools run in your process, so what the trace shows is what you instrument: the gateway sees the model calls, and a tool span appears only if the framework emits one (LangGraph does) or you decorate the dispatch yourself (module 02, step 3). A managed agent is the exception: orq executes server-side tools, and the retrieval or delegation lands in the trace without you doing anything.

## Two things the comparison exposes

**Leg 2 speaks a different protocol, and it shows.** LangGraph goes through `/chat/completions`, where GPT-5.x rejects tool definitions unless `reasoning_effort="none"`, a real 400 already documented in [troubleshooting](reference/troubleshooting.md). Legs 1 and 3 use the Responses API, where the question never arises. So the three traces are comparable in content but not span-for-span identical.

**Instrumenting nothing has a price.** Legs 1 and 3 get a trace id back on the response itself. Leg 2 never touches the graph, so it has to name the run and look the trace up afterwards, once the gateway has indexed it. Zero-touch instrumentation costs you the immediate handle.

## Choosing

- **Your own loop** when the control flow is the product: explicit steps, your own retries, your own state. You keep every seam and give up nothing but convenience.
- **A framework** when the graph is worth having and you want the ecosystem. One line of setup and orq observes it.
- **A managed agent** when the agent is configuration rather than code, and you want prompts, tools and versions changeable without a deploy, at the cost of the loop running somewhere you cannot step through.

The three are not exclusive. A managed agent can call tools your service exposes over MCP ([module 10](modules/10.md)); a framework agent can read a knowledge base orq hosts ([module 09](modules/09.md)); all three land in the same traces, the same budgets and the same evaluations.

## Related

- [`examples/own-your-agent.py`](https://github.com/orq-ai/orq-workshop/blob/main/examples/own-your-agent.py): the script behind this page
- [Module 08 · Managed agents](modules/08.md) · [Module 02 · Tracing](modules/02.md) · [How retrieval works](reference/rag.md)
- [orq.ai · Tracing LangGraph](https://orq.ai/blog/tracing-langgraph-orq-ai) · [Building a LangGraph agent on orq.ai](https://orq.ai/blog/langgraph-agent-orq-ai)
