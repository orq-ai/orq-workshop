---
hide: [navigation]
---

# orq.ai workshop

Hands-on training for teams building on [orq.ai](https://orq.ai). One sample app, a customer-support refund agent, grows module by module: through the AI Gateway, behind guardrails, into traces, under evaluation, as a managed agent with a knowledge base and MCP tools, attacked by simulated users and red teams, gated in CI, and driven by coding agents.

[Start with module 00](modules/00.md){ .md-button .md-button--primary }
[See the agenda](agenda.md){ .md-button }

<div class="grid cards" markdown>

-   :material-router:{ .lg .middle } **AI Gateway track**

    ---

    Gateway, tracing, smart routing, guardrails and PII, budgets, troubleshooting with orqi, failure analysis to evaluators to experiments.

    [:octicons-arrow-right-24: Modules 00 to 07](modules/00.md)

-   :material-robot:{ .lg .middle } **Managed Agents track**

    ---

    Managed agents, knowledge base and RAG, MCP servers and the MCP Gateway, simulation and red teaming, evals and headless agents in CI, coding agents.

    [:octicons-arrow-right-24: Modules 08 to 13](modules/08.md)

-   :material-new-box:{ .lg .middle } **What's new**

    ---

    Features from orq 4.10 to 4.14 and orq-cli 8.x, and the module where each one shows up.

    [:octicons-arrow-right-24: What's new](whats-new.md)

-   :material-format-list-numbered:{ .lg .middle } **12-Factor Agents**

    ---

    The design spine. Every module names the factor it exercises and the orq surface that embodies it.

    [:octicons-arrow-right-24: The map](twelve-factor.md)

-   :material-human-male-board:{ .lg .middle } **Instructor**

    ---

    Facilitator notes, seeded failures, reset commands, and the live-session deck.

    [:octicons-arrow-right-24: Facilitator notes](instructor/index.md)

-   :material-book-open-variant:{ .lg .middle } **Reference**

    ---

    Cheat sheet, troubleshooting table, glossary.

    [:octicons-arrow-right-24: Cheat sheet](reference/cheat-sheet.md)

</div>

## How to work through it

Each module has a `README.md` (the lesson), a `run.py` (the starter), a `solution/` (the finished exercise) and an `agent_prompt.md` (the same exercise handed to a coding agent). Every module ends with a **Done when** checklist that you can verify in the Studio. Modules build on each other, but `make seed` creates every prerequisite entity so you can jump in anywhere.

Two ways to work, side by side. **By hand**: the SDK, the CLI, the Studio. **With your coding agent**: `orq launch claude` (or `opencode`, `pi`, `codex`) and paste the prompt. Both leave the same traces.
