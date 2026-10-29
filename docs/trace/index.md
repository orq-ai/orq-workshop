<p class="stage-chip">Academy · the idea, no code · <a href="../start/academy/">all six stages</a></p>

# Trace

## The problem

A customer writes to Lumen Goods on Thursday: "Your chat said my refund for ord_a3 was approved, then the next message said it was refused. Which is it?" Support opens the ticket and finds the customer's name and nothing else. The refund agent logs each model call as a line in the application log: a timestamp, a token count, a status code. There are nine lines from that hour. Nobody can say which three belong to this customer, in which order, or what the order lookup returned before the agent changed its mind.

An engineer spends the afternoon on it. She reconstructs the conversation from the chat database, guesses which model calls match by timestamp, and still cannot see the tool results, because the tools run in the application and never logged their output. The agent was probably right to refuse: ord_a3 is outside the 30-day window and the customer gave no evidence. But "probably" is the whole problem. The team cannot defend a decision it cannot replay.

## The idea

A trace is the full record of one unit of work, as a tree. The root is the customer turn. Under it are the spans: the agent's reasoning step, each tool call with its input and output, and each model call with the prompt, the answer, the model that answered, the tokens and the cost. Read top to bottom it is the story of that turn; read across many turns it is the data the next three stages run on. Logs are lines; traces are trees with timing and parentage.

| | A log line | A trace |
|---|---|---|
| Unit | one event | one turn, with everything inside it |
| Shows | that something happened | what was asked, what came back, and what it cost |
| Linked by | a timestamp, by luck | a trace id and a parent span |
| Answers | "did the call fail?" | "why did the agent refuse this customer?" |

The question underneath every tracing setup is who produces which span. The gateway sees every model call that passes through it, so those spans come for free: prompt, answer, model, cost. The gateway cannot see what it never receives: the tool that looked the order up, the policy text that was read, the step that decided to refuse. Those spans come from your code, or from the framework if it emits them, and they are the ones that explain a decision.

![Diagram: who produces which span. The application emits the root span for the refund turn and its three tool spans; the gateway emits one trace per model call, nested under the root because the application passes the trace context along with the request; the request's name, identity, thread and metadata become filters in the traces view.](../modules/tracing/assets/span-ownership.png)

Two mechanisms join the halves. The application opens the root span and passes its context to the gateway on every model call, so the gateway's spans nest under it instead of starting a new trace. And the request carries a few fields that become filters later: a name for the operation, an identity for the customer, a thread for the conversation, and free metadata such as the customer's plan. With those four fields, "show me every turn of this customer this week, grouped by conversation" is a filter, not an investigation.

Instrumentation effort comes in three sizes. Nothing: route calls through the gateway and you have the model spans. One line: a framework callback that turns every node and tool into a span. A few decorators: wrap your agent step and your tools yourself, and export over the open telemetry standard if you already run it. Pick the smallest size that shows the decision you will need to defend.

## What good looks like

- [ ] One trace per customer turn, with the tool inputs and outputs inside it, not only the model calls.
- [ ] Every trace carries the customer identity and the conversation id, so one complaint is one filter.
- [ ] Cost and latency per turn are read from the trace, not estimated from the invoice.
- [ ] The trace you look at from a bug report is the same trace the evaluation stage reads.
- [ ] A new engineer can find the trace behind a complaint within a minute, without asking anyone.

## Where teams start

Let's assume you have nothing yet. Route the model calls through the gateway and open one trace in the viewer. Then add the identity and thread fields to the request; that alone turns a pile of calls into conversations per customer. Add tool spans when the first "why did it do that" question arrives, which will be soon.

Let's assume you have an app in production with logging and maybe an observability stack. Keep the stack: export the agent spans over the open standard and let the gateway's spans nest under them by passing the trace context. The goal is one tree per turn, not a second dashboard. Then delete the log lines that the trace now covers.

## On orq.ai

On orq.ai every call through the AI Gateway is a trace in the Studio's Traces view, with the model, prompt, answer, tokens and cost. The request body fields `name`, `identity`, `thread` and `metadata` become filters in the Studio and in the traces search API. The W3C `traceparent` header tells the gateway to continue your trace instead of starting its own. Spans the gateway cannot see come from the `traced` decorator in the Python SDK, typed as agent or tool, or from a one-line LangChain callback; both can export over OTLP to the orq.ai OpenTelemetry endpoint. Threads group the turns of one conversation, and the same trace later feeds Insights, annotation queues, evaluators and alerts. Read [Traces](https://docs.orq.ai/ai-studio/observability/traces).

## Practice it

- [Tracing](../modules/tracing.md) (core path)

## For leaders

**Cost.** Hours, not days: the gateway traces model calls for free, and tool spans are a few decorators.

**Risk.** Without traces every complaint is an investigation, and every quality claim is an opinion.

**Owner.** The team that owns the agent; the observability team owns where the spans are exported.

**Ask your team.** Can you show me the full conversation behind one complaint, within a minute?
