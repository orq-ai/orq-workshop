---
hide: [navigation]
---

# orq.ai workshop

Hands-on training for teams building on [orq.ai](https://orq.ai). One sample app, a customer-support refund agent, grows module by module: through the AI Gateway, behind guardrails, into traces, under evaluation, as a managed agent with a knowledge base and MCP tools, attacked by simulated users and red teams, gated in CI, and driven by coding agents.

The site has two layers around the same loop. The **Academy** explains each stage: the idea, what good looks like, no code, about an hour. The **Workshop** practices it: hands-on modules on orq.ai, about four hours for the core path.

[Academy: the ideas](start/academy.md){ .md-button }
[Workshop: hands-on](start/for-engineers.md){ .md-button .md-button--primary }

Already on orq.ai? Go to the [electives by stage](start/already-on-orq.md).

<div class="grid cards" markdown>

-   :material-hammer-wrench:{ .lg .middle } **Build**

    ---

    The refund agent as a managed agent, with a knowledge base, MCP tools and delegation.

    [:octicons-arrow-right-24: Build](build/index.md)

-   :material-router:{ .lg .middle } **Route and protect**

    ---

    Fallbacks and cache, smart routing, guardrails and PII, budgets and keys: every call goes through the gateway.

    [:octicons-arrow-right-24: Route and protect](route/index.md)

-   :material-chart-timeline-variant:{ .lg .middle } **Trace**

    ---

    Every model call, tool result and decision, readable after the fact, grouped by customer and conversation.

    [:octicons-arrow-right-24: Trace](trace/index.md)

-   :material-magnify-scan:{ .lg .middle } **Find failures**

    ---

    Turn traces into a failure taxonomy, by hand, with a skill, with Insights, and with human review.

    [:octicons-arrow-right-24: Find failures](find-failures/index.md)

-   :material-clipboard-check:{ .lg .middle } **Evaluate**

    ---

    Evaluators, datasets and experiments, simulated customers, red teams.

    [:octicons-arrow-right-24: Evaluate](evaluate/index.md)

-   :material-shield-check:{ .lg .middle } **Gate and monitor**

    ---

    A regression gate in CI, alerts on cost and errors, webhooks into your own systems.

    [:octicons-arrow-right-24: Gate and monitor](gate/index.md)

</div>

## The loop

One agent goes around the loop; every stage reads what the previous one left. The core path visits each stage once, in this order, in about four hours.

![Diagram: the orq.ai loop, six stages around the refund agent: Build, Route and protect, Trace, Find failures, Evaluate, Gate and monitor, and back to Build.](assets/diagrams/orq-loop.png)

## How the pieces fit

One credential opens every door: your code and your coding agent both go through the AI Gateway, the managed agent hands its tool calls back to your code, and everything lands as traces in the Studio.

![Diagram: how the workshop pieces fit. The refund agent and a coding agent on your machine call the orq AI Gateway, which routes to model providers, hosts the managed agent whose function_call items come back to your code, and sends traces to the Studio; the coding agent also talks to the orq MCP server.](assets/diagrams/workshop-map.png)

## How to work through it

Each module has a `README.md` (the lesson), a `run.py` (the starter; the finished exercise is at the same path on the [`solution` branch](https://github.com/orq-ai/orq-workshop/tree/solution)) and an `agent_prompt.md` (the same exercise handed to a coding agent). Every module ends with a **Done when** checklist that you can verify in the Studio. Each module closes with links to the matching pages on [docs.orq.ai](https://docs.orq.ai); the [cheat sheet](reference/cheat-sheet.md) collects them. Modules build on each other, but `make seed-workspace` creates every prerequisite entity so you can jump in anywhere.

Prefer a notebook? Check out the `solution` branch, then `make lab` opens JupyterLab with one notebook for every module whose `run.py` is written in Jupytext percent format (`make notebooks` prints the list): the finished module split into steps, explanation above each cell. The generated files carry no saved output; run a cell to see its result. On `main` the starters are plain scripts, so there is nothing to generate.

Two ways to work, side by side. **By hand**: the SDK, the CLI, the Studio. **With your coding agent**: `orq launch claude` (or `opencode`, `pi`, `codex`) and paste the prompt. Both leave the same traces.
