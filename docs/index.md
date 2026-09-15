---
hide: [navigation]
---

# orq.ai workshop

Hands-on training for teams building on [orq.ai](https://orq.ai). One sample app, a customer-support refund agent, grows module by module: through the AI Gateway, behind guardrails, into traces, under evaluation, as a managed agent with a knowledge base and MCP tools, attacked by simulated users and red teams, gated in CI, and driven by coding agents.

[Start with Setup](modules/00.md){ .md-button .md-button--primary }
[See the agenda](agenda.md){ .md-button }

<div class="grid cards" markdown>

-   :material-router:{ .lg .middle } **AI Gateway**

    ---

    Fallbacks and cache, smart routing and routing rules, guardrails and PII, budgets, keys and identities.

    [:octicons-arrow-right-24: Modules 01, 03, 04, 05](modules/01.md)

-   :material-chart-timeline-variant:{ .lg .middle } **AI Observability**

    ---

    Tracing, troubleshooting with orqi, failure analysis to evaluators to experiments, alerts and webhooks, annotation queues and automations.

    [:octicons-arrow-right-24: Modules 02, 07, 14, 17](modules/02.md)

-   :material-robot:{ .lg .middle } **Managed Agents**

    ---

    Managed agents, knowledge base and RAG, MCP servers and the MCP Gateway, agent simulation, evals and headless agents in CI, coding agents, advisor and sidekick, red teaming.

    [:octicons-arrow-right-24: Modules 08 to 12, 15, 16](modules/08.md)

-   :material-new-box:{ .lg .middle } **What's new**

    ---

    Features from orq 4.10 to 4.14 and orq-cli 8.x, and the module where each one shows up.

    [:octicons-arrow-right-24: What's new](whats-new.md)

-   :material-human-male-board:{ .lg .middle } **Instructor**

    ---

    Facilitator notes, seeded failures, reset commands, and the live-session deck.

    [:octicons-arrow-right-24: Facilitator notes](instructor/index.md)

-   :material-book-open-variant:{ .lg .middle } **Reference**

    ---

    Cheat sheet, troubleshooting table, glossary.

    [:octicons-arrow-right-24: Cheat sheet](reference/cheat-sheet.md)

</div>

## How the pieces fit

One credential opens every door: your code and your coding agent both go through the AI Gateway, the managed agent hands its tool calls back to your code, and everything lands as traces in the Studio.

![Diagram: how the workshop pieces fit. The refund agent and a coding agent on your machine call the orq AI Gateway, which routes to model providers, hosts the managed agent whose function_call items come back to your code, and sends traces to the Studio; the coding agent also talks to the orq MCP server.](assets/diagrams/workshop-map.png)

## How to work through it

Each module has a `README.md` (the lesson), a `run.py` (the starter), a `solution/` (the finished exercise) and an `agent_prompt.md` (the same exercise handed to a coding agent). Every module ends with a **Done when** checklist that you can verify in the Studio. Each module closes with links to the matching pages on [docs.orq.ai](https://docs.orq.ai); the [cheat sheet](reference/cheat-sheet.md) collects them. Modules build on each other, but `make seed` creates every prerequisite entity so you can jump in anywhere.

Prefer a notebook? `make lab` opens JupyterLab with one notebook per module where it fits (01, 02, 03, 04, 08, 09): the solution split into steps, explanation above each cell, output below. They are generated from `solution/run.py`, so they never drift from the script.

Two ways to work, side by side. **By hand**: the SDK, the CLI, the Studio. **With your coding agent**: `orq launch claude` (or `opencode`, `pi`, `codex`) and paste the prompt. Both leave the same traces.
