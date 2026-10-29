---
hide: [navigation]
---

# orq.ai workshop

Hands-on training for teams building on [orq.ai](https://orq.ai). One sample app, a customer-support refund agent, grows module by module: through the AI Gateway, behind guardrails, into traces, under evaluation, as a managed agent with a knowledge base and MCP tools, attacked by simulated users and red teams, gated in CI, and driven by coding agents.

[Start with Setup](modules/00.md){ .md-button .md-button--primary }
[See the agenda](agenda.md){ .md-button }

<div class="grid cards" markdown>

-   :material-tools:{ .lg .middle } **Setup**

    ---

    The orq CLI and your keys, the orqi harness, troubleshooting a failing run, and handing the same exercise to a coding agent.

    [:octicons-arrow-right-24: Setup, orqi troubleshooting, coding agents](modules/00.md)

-   :material-router:{ .lg .middle } **AI Gateway**

    ---

    Fallbacks and cache, smart routing and routing rules, guardrails and PII, MCP servers and the MCP Gateway.

    [:octicons-arrow-right-24: Gateway, routing, guardrails, MCP](modules/01.md)

-   :material-chart-timeline-variant:{ .lg .middle } **AI Observability**

    ---

    Tracing across your code and the gateway, alerts and webhooks, annotation queues and trace automations.

    [:octicons-arrow-right-24: Tracing, alerts, annotation queues](modules/02.md)

-   :material-robot:{ .lg .middle } **Managed agents**

    ---

    The same agent three ways: your loop, a framework's, orq's, then managed agents, and delegation with advisor and sidekick.

    [:octicons-arrow-right-24: Build your own agent](own-your-agent.md)

-   :material-database-search:{ .lg .middle } **RAG and Retrieval**

    ---

    How retrieval actually works (chunking, embeddings, search modes, reranking) and a knowledge base wired three ways.

    [:octicons-arrow-right-24: How retrieval works](reference/rag.md)

-   :material-clipboard-check:{ .lg .middle } **Evaluation**

    ---

    evaluatorq and orq-arena, failure analysis to evaluators to experiments, agent simulation, red teaming, and the whole thing gated in CI.

    [:octicons-arrow-right-24: evaluatorq](reference/evaluatorq.md)

-   :material-shield-key:{ .lg .middle } **Administration**

    ---

    Budgets per identity, keys and Management Keys, and the Terraform provider that declares them.

    [:octicons-arrow-right-24: Budgets and keys](modules/05.md)

-   :material-book-open-variant:{ .lg .middle } **Reference**

    ---

    Cheat sheet, troubleshooting table, glossary.

    [:octicons-arrow-right-24: Cheat sheet](reference/cheat-sheet.md)

</div>

## How the pieces fit

One credential opens every door: your code and your coding agent both go through the AI Gateway, the managed agent hands its tool calls back to your code, and everything lands as traces in the Studio.

![Diagram: how the workshop pieces fit. The refund agent and a coding agent on your machine call the orq AI Gateway, which routes to model providers, hosts the managed agent whose function_call items come back to your code, and sends traces to the Studio; the coding agent also talks to the orq MCP server.](assets/diagrams/workshop-map.png)

## How to work through it

Each module has a `README.md` (the lesson), a `run.py` (the starter; the finished exercise is at the same path on the [`solution` branch](https://github.com/orq-ai/orq-workshop/tree/solution)) and an `agent_prompt.md` (the same exercise handed to a coding agent). Every module ends with a **Done when** checklist that you can verify in the Studio. Each module closes with links to the matching pages on [docs.orq.ai](https://docs.orq.ai); the [cheat sheet](reference/cheat-sheet.md) collects them. Modules build on each other, but `make seed-workspace` creates every prerequisite entity so you can jump in anywhere.

Prefer a notebook? Check out the `solution` branch, then `make lab` opens JupyterLab with one notebook for every module whose `run.py` is written in Jupytext percent format (`make notebooks` prints the list): the finished module split into steps, explanation above each cell. The generated files carry no saved output; run a cell to see its result. On `main` the starters are plain scripts, so there is nothing to generate.

Two ways to work, side by side. **By hand**: the SDK, the CLI, the Studio. **With your coding agent**: `orq launch claude` (or `opencode`, `pi`, `codex`) and paste the prompt. Both leave the same traces.
