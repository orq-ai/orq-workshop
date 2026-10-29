<p class="stage-chip">Academy · stage 3 of 6 · 8 min read · <a href="../">all six stages</a></p>

<nav class="loop-map" data-current="trace">
<a class="loop-stage" data-stage="build" data-mode="development" href="../build/">Build</a>
<a class="loop-stage" data-stage="route" data-mode="production" href="../route/">Route and protect</a>
<a class="loop-stage" data-stage="trace" data-mode="production" href="../trace/">Trace</a>
<a class="loop-stage" data-stage="find-failures" data-mode="development" href="../find-failures/">Find failures</a>
<a class="loop-stage" data-stage="evaluate" data-mode="development" href="../evaluate/">Evaluate</a>
<a class="loop-stage" data-stage="gate" data-mode="production" href="../gate/">Gate and monitor</a>
</nav>

# Trace

See exactly what your AI did, for any customer, after the fact. With orq.ai every call your agent makes is recorded as one readable story, and every later stage of the loop reads from those stories.

## You need this when…

<div class="symptoms">
<p class="symptom">A customer complains about an answer, and nobody on the team can show what the agent saw or did.</p>
<p class="symptom">The team argues about whether a problem is the model, the prompt or your own data, and there is no way to settle it.</p>
<p class="symptom">Finance asks what one conversation costs, and the answer is the monthly invoice.</p>
<p class="symptom">You are about to put an agent in front of customers and cannot say how you would investigate its first incident.</p>
</div>

## What's going on

An agent does not make one call. It makes a chain of them: it reads the message, decides, asks your systems for an order or a policy, reads the answer, and replies. An application log records each call on its own line, with a time, a token count and a status. Nothing ties the lines of one conversation together, and the answers your own systems gave the agent are usually not there at all.

A trace keeps the chain together. Below are nine log lines from one hour of support chat for Lumen Goods, the shop the refund agent works for. One of them belongs to a customer who complained: the chat told her the refund for her order was approved, then said it was refused. Step through it.

<div class="explainer" data-explainer>
<div class="explainer-stage">
<div data-group-by="customer">
<div class="log-group-label" data-customer="a">Ana · order ord_a3 · the complaint</div>
<div class="log-line" data-customer="a">10:02:11 · gpt-6-luna · 412 tok · 200</div>
<div class="log-group-label" data-customer="b">Ben · order ord_b1</div>
<div class="log-line" data-customer="b">10:02:19 · gpt-6-luna · 388 tok · 200</div>
<div class="log-group-label" data-customer="c">Chloé · order ord_b3</div>
<div class="log-line" data-customer="c">10:02:40 · gpt-6-luna · 455 tok · 200</div>
<div class="log-line" data-customer="b">10:03:02 · gpt-6-luna · 301 tok · 200</div>
<div class="log-line" data-customer="a">10:04:05 · gpt-6-luna · 290 tok · 200</div>
<div class="log-line" data-customer="c">10:04:31 · gpt-6-luna · 512 tok · 200</div>
<div class="log-line" data-customer="a">10:04:33 · gpt-6-luna · 604 tok · 200</div>
<div class="log-line" data-customer="b">10:05:12 · gpt-6-luna · 277 tok · 200</div>
<div class="log-line" data-customer="c">10:05:40 · gpt-6-luna · 340 tok · 200</div>
</div>
<div class="span-tree">
<p class="span-turn" id="t1">Turn 1 · "Can I get a refund for ord_a3?"</p>
<div class="span" id="s1"><span class="span-kind">agent</span>refund agent</div>
<div class="span-gap" id="g1">No order lookup: the agent answered without checking the order</div>
<div class="span child" id="s2"><span class="span-kind">model</span>answers: "approved"</div>
<p class="span-turn" id="t2">Turn 2 · "So the refund is approved?"</p>
<div class="span" id="s3"><span class="span-kind">agent</span>refund agent</div>
<div class="span child" id="s4"><span class="span-kind">model</span>decides to look the order up</div>
<div class="span child" id="s5"><span class="span-kind">tool</span>lookup_order(ord_a3)</div>
<div class="span-output" id="o5">{"ok": true, "order": {"id": "ord_a3", "item": "Cable organiser set", "amount": 42.5, "delivered_days_ago": 45, "within_standard_window": false}}</div>
<div class="span child" id="s6"><span class="span-kind">model</span>answers: outside the 30-day window</div>
</div>
</div>
<ol class="explainer-steps">
<li data-show="">Nine log lines from one hour of support chat. Each is one model call: a time, a token count, a status. Which ones belong to the customer who complained?</li>
<li data-show="" data-group>The same nine calls, grouped by customer and conversation. Ana's three calls are now together. That grouping is what a trace gives you.</li>
<li data-show="t1 s1 s2" data-hot="s1 s2">Ana's first turn. The agent answered "approved". Two steps: the agent, then the model. Something is missing.</li>
<li data-show="g1" data-bad="s2 g1">There is no order lookup. The agent promised a refund without checking the order. In a log, a missing step is invisible. In a trace, it is a gap in the tree.</li>
<li data-show="t2 s3 s4 s5 o5" data-hot="s5 o5">Ana's second turn. This time the agent looked the order up, and your own system answered: delivered 45 days ago, outside the standard window.</li>
<li data-show="s6" data-hot="s6">So the second answer was right, and the cause is the first turn skipping the lookup. Found in under a minute, with the cost and duration of every step on the same screen.</li>
</ol>
</div>

## Logs versus traces

| Question you will be asked | Application logs | Traces |
|---|---|---|
| What did the agent tell this customer, and why? | Rebuilt by hand from timestamps | Open the conversation |
| What did your own systems return to the agent? | Usually not recorded | Every tool call and its result |
| Was it the model, the prompt or your data? | Opinion | Visible step by step |
| What does one conversation cost? | The monthly invoice, divided by a guess | Per conversation and per step |
| Can you test the fix on the real case? | No | The trace becomes a test case in the next stage |

## What orq.ai does

- **Traced by default.** Every call that goes through the orq.ai AI Gateway is traced, with the prompt, the answer, cost, tokens and latency. Agents hosted on orq.ai are traced the same way.
- **The whole chain in one tree.** Agent, model and tool steps nest in one trace, with the inputs and outputs of each step.
- **Grouped by customer and conversation.** Tag calls with who they were for (an identity) and which conversation they belong to (a thread), and the orq.ai Studio groups and filters on both.
- **Your existing stack too.** Frameworks such as LangGraph or the OpenAI Agents SDK send their traces to orq.ai over OpenTelemetry, the open standard for traces.

## Four ways to get traces into orq.ai

Which one fits depends on how your app talks to models today. Most teams combine two. Pick the situation that sounds like your team.

<div class="chooser" data-chooser>
<div class="chooser-options">
<button type="button" data-lights="way-gateway" data-why="Change the base URL and every model call is traced, with cost, latency and the full prompt. Add an identity and a thread so calls group by customer and conversation.">We call model providers from our own code, and changing the base URL is fine.<span class="chooser-reason">Change the base URL and every model call is traced, with cost, latency and the full prompt. Add an identity and a thread so calls group by customer and conversation.</span></button>
<button type="button" data-lights="way-gateway way-sdk" data-why="The gateway traces the model calls; the orq.ai SDK adds your own steps, the agent turn and each tool, around them, and both land in one tree. This is what the Workshop builds.">We run our own agent loop and want to see our tools, not only the model calls.<span class="chooser-reason">The gateway traces the model calls; the orq.ai SDK adds your own steps, the agent turn and each tool, around them, and both land in one tree. This is what the Workshop builds.</span></button>
<button type="button" data-lights="way-otel" data-why="Keep your framework and your provider. The framework sends OpenTelemetry to orq.ai, so the traces read the same. orq.ai has setup guides for LangGraph, the OpenAI Agents SDK and many others.">We use a framework such as LangGraph, or must keep calling providers directly.<span class="chooser-reason">Keep your framework and your provider. The framework sends OpenTelemetry to orq.ai, so the traces read the same. orq.ai has setup guides for LangGraph, the OpenAI Agents SDK and many others.</span></button>
<button type="button" data-lights="way-hosted" data-why="Agents hosted on orq.ai are traced end to end, every tool call included, without any instrumentation on your side.">We would rather orq.ai runs the agent for us.<span class="chooser-reason">Agents hosted on orq.ai are traced end to end, every tool call included, without any instrumentation on your side.</span></button>
</div>
<div class="chooser-ways">
<div class="chooser-way" id="way-gateway"><strong>AI Gateway</strong>No instrumentation: route your calls through orq.ai. Sees every model call.</div>
<div class="chooser-way" id="way-sdk"><strong>orq.ai SDK</strong>Mark your own functions as agent or tool steps. Sees your steps, nested with the gateway's.</div>
<div class="chooser-way" id="way-otel"><strong>OpenTelemetry</strong>The open standard: your framework exports to orq.ai. Sees whatever your framework records.</div>
<div class="chooser-way" id="way-hosted"><strong>Hosted agents</strong>The agent runs on orq.ai. Sees everything, by default.</div>
<div class="chooser-why" aria-live="polite">Pick the situation that sounds like your team.</div>
</div>
</div>

<section class="storyboard" data-clip="3" data-status="awaiting" markdown>

<p class="storyboard-title"><strong>Clip 3 · From a complaint to the cause</strong></p>

<ul class="storyboard-meta">
<li><strong>Audience:</strong> team leaders, in the stage walk of the leaders' session</li>
<li><strong>Point it makes:</strong> one complaint, the full conversation, the exact cause, in under a minute</li>
<li><strong>Length:</strong> about 90 seconds, captions only</li>
<li><strong>Source:</strong> the orq.ai Studio, project orq-academy, scripted traffic</li>
<li><strong>Also on screen:</strong> project switcher closed; the workspace name is visible in the header</li>
</ul>

| # | Time | On screen | Caption |
|---|---|---|---|
| 1 | 0:00-0:08 | The complaint: "Your chat said my refund for ord_a3 was approved, then it said refused." | A customer complains. Which answer was right, and why did it change? |
| 2 | 0:08-0:20 | Studio, Traces, filtered on the customer's identity: one conversation, two turns | Every conversation is recorded, grouped by customer. |
| 3 | 0:20-0:40 | Turn 1 opened: the agent span and one model span, no tool span | The first answer came without looking at the order. |
| 4 | 0:40-0:58 | Turn 2 opened: the `lookup_order` tool span and its output, zoomed on `delivered_days_ago: 45` | The order is outside the 30-day window. The second answer was right. |
| 5 | 0:58-1:15 | Back to turn 1, the gap highlighted | The bug: turn 1 skipped the lookup. Found in under a minute. |
| 6 | 1:15-1:30 | Cost and latency in the trace header; end card "Workshop: tracing" | Cost and speed come with every trace. Engineers build this in the tracing module. |

**To approve:** say "approve clip 3", or change any row. Nothing is recorded before that.

</section>

## What it takes

<div class="takes">
<div class="take"><em>Who</em><strong>One engineer</strong>No change to how the rest of the team works.</div>
<div class="take"><em>How long</em><strong>Half a day</strong>Point the app at the gateway, add identity and thread. Thirty minutes in the Workshop.</div>
<div class="take"><em>First</em><strong>Calls go through orq.ai</strong>Route and protect comes before this, or an OpenTelemetry exporter if you keep your own client.</div>
</div>

## When you don't need it yet

A prototype that only your own team uses, where you read every conversation yourselves. Turn tracing on the day the first outside user arrives: it is cheap to add then, and the first incident is never the moment to add it.

## What good looks like

- Anyone on support can find the full conversation behind a complaint in under a minute.
- Every trace names a customer and a conversation.
- Tool results are in the trace, not only the model's words.
- Cost per conversation is a number the team knows.

Leaders score this list at the readout at the end of the first week.

## Next

<div class="grid cards" markdown>

-   **Workshop · for engineers**

    ---

    [Tracing](../modules/tracing.md), 30 minutes: agent, tool and model steps with identity and thread, on the refund agent, then on your own app.

-   **Academy · stage 4**

    ---

    [Find failures](find-failures.md): thousands of traces, a handful of ways the agent goes wrong.

</div>

!!! info "Terms on this page"
    - **Trace:** the full record of one unit of work, such as one customer turn, as a tree of steps.
    - **Span:** one step in that tree: a model call, a tool call, the agent itself.
    - **Identity:** who the call was for: a customer, a team, a client.
    - **Thread:** which conversation a call belongs to, across turns.
    - **Tool call:** the agent asking your systems for something: an order, a policy, a refund.
