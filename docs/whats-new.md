# What's new in orq

Features from recent releases that this workshop uses, and the module where each one shows up. Refresh this page before every client run: `orqi /whatsnew` prints the current changelog. Full notes at [docs.orq.ai/changelog](https://docs.orq.ai/docs/changelog).

| Release | Feature | Module |
|---|---|---|
| 4.14 | **MCP Portal**: MCP Servers and MCP Gateway in one place. Gateway bundles upstream servers behind `/v3/mcp/<key>`, exposes all, selected or none of each server's tools, logs every call including denied ones. Code Mode vs Direct Mode. | [10](modules/10.md) |
| 4.14 | Guardrail and evaluator indicators on every trace span; time-range selector; search by id. | [02](modules/02.md), [04](modules/04.md) |
| 4.14 | OpenAI Codex sessions captured as traces; CLI onboarding in the Studio. | [13](modules/13.md) |
| 4.13 | **Smart Router** page with model bands from an intelligence index, `route_pool` over N candidates, quality / balanced / cost profiles. | [03](modules/03.md) |
| 4.13 | **Advisor and Sidekick** tools: an agent consults a second model mid-turn, or delegates a discrete task. Metered separately, own spans. | [08](modules/08.md) |
| 4.13 | Guardrail sampling and non-blocking mode for system guardrails; redesigned thread view; span-to-source links; `store: false` on Responses. | [04](modules/04.md), [02](modules/02.md) |
| 4.12 | **System guardrails**: built-in PII Detection and Secret Detection, fail-closed, monitor mode. PII redaction up to 10x faster. | [04](modules/04.md) |
| 4.12 | Filter traces by number of messages; configurable tool timeout per agent tool. | [02](modules/02.md), [08](modules/08.md) |
| 4.11 | **Budgets** as a first-class entity: workspace, project, identity, API key, provider or model scope; cost, token or requests-per-minute limits; alerts; Management Keys. | [05](modules/05.md) |
| 4.11 | **PII redaction plugin**: placeholders before the provider, originals restored on the way back, workspace or request level. | [04](modules/04.md) |
| 4.11 | Memory Stores UI; Human Review renamed **Annotations** with queues and an API; MCP setup timing as spans; incremental streaming on the router. | [08](modules/08.md), [02](modules/02.md) |
| 4.10 | Broader framework tracing: LangGraph, Vercel AI SDK, Pydantic AI, Mastra, Agno, Google ADK, Claude Agent SDK. `invoke_model` MCP tool with reasoning options. | [02](modules/02.md) |
| 4.9 | LangGraph graph view next to its trace; global LangChain callback registration. | [02](modules/02.md) |
| 4.6 | **Red teaming** in evaluatorq: OWASP LLM Top 10 and Agentic (ASI) categories, agent-aware attacks, exit-code gating, results as Experiment runs. **Auto Router**. | [11](modules/11.md), [12](modules/12.md) |
| CLI 8.x | `orq launch <agent>` (session-only gateway routing, MCP and skills), `orq connect --local` (permanent wiring per project), `orq traces thread`, `orq traces insights`, `orq doctor`, `orq orqi`. | [00](modules/00.md), [06](modules/06.md), [13](modules/13.md) |
| orqi | Terminal helper agent with 43 orq MCP tools, the orq skills plus seven of its own (`investigate-root-cause`, `debug-conversation`, `workspace-health-check`, `optimize-cost`, `setup-guardrails`, `manage-knowledge-base`, `platform-guide`). Alpha. | [06](modules/06.md), [12](modules/12.md) |

!!! note "Naming drift worth knowing"
    On Agents the delegation tools are `advisor` and `sidekick`. On the gateway's server tools they are `orq:advisor` and `orq:subagent`; `orq:sidekick` is a legacy alias. The MCP Tool type on agents is retired: MCP connections are managed in the MCP Portal.
