# What's new in orq.ai

Features from recent releases that this workshop uses, and the module where each one shows up. Refresh this page before every client run: `orqi /whatsnew` prints the current changelog. Full notes at [docs.orq.ai/changelog](https://docs.orq.ai/docs/changelog).

| Release | Feature | Module |
|---|---|---|
| 4.16 | **Traces page** rebuilt: any attribute or metadata field as a filter or a column, OQL query bar, activity chart follows the query, filters, columns and time range in the URL. `GET /v3/traces/{trace_id}/conversation` returns a trace as ordered messages. | [Tracing](modules/02.md) |
| 4.16 | Cached and cache-write tokens on the span panel; the Deployment variant or Agent version on every LLM span. | [Tracing](modules/02.md), [Managed agents](modules/08.md) |
| 4.16 | **Monitors** (Beta): widget pages over Traces, Metrics and Logs, alert from a widget. **Logs** (Beta): OpenTelemetry logs at `/v2/otel/v1/logs`, Logs Explorer. | [Alerts and webhooks](modules/14.md) |
| 4.16 | Python evaluators return `{"value": ..., "explanation": ...}`, explanation shown next to the score; `llm.evaluator` webhook event for every evaluator result. | [Failure analysis and evals](modules/07.md), [Alerts and webhooks](modules/14.md) |
| 4.16 | **Decisions API** (Beta): `POST /v3/router/decisions` answers yes/no, multiple-choice and scored questions with probabilities, natively on `typesafe/jev-latest`. A dataset created with `path` and `project_id` lands in that project. | [Failure analysis and evals](modules/07.md) |
| 4.16 | orq.ai skills `orq-recommend-evaluators` (new) and `orq-evaluator-alignment` (judge tested against a jury of models), installed with `npx skills add orq-ai/assistant-plugins`. | [Failure analysis and evals](modules/07.md), [Coding agents](modules/13.md) |
| 4.16 | API Keys tab in the Home usage table; Azure cached token pricing; Audit Logs date filter. Keys created with a management key (`POST /v2/api-keys`) take a project, permissions and expiry; from a user login, `orq api-keys create --expires-at` still returned `unknown field "expires_at"` on 13 Oct 2026. | [Budgets and keys](modules/05.md) |
| 4.16 | Evaluators and guardrails follow the plugins configured on the call, so PII redaction applies to them too. | [Guardrails](modules/04.md) |
| 4.16 | Tool schema editor validates each parameter type and points to the error. | [Managed agents](modules/08.md) |
| 4.16 | Streamed model calls through the router run up to 30 minutes (was 10); `limits.max_execution_time` still wins. | [Gateway](modules/01.md) |
| 4.15 | **orq.ai CLI** (Beta): `orq setup` signs in and wires every detected agent; `orq launch <agent>`, `-p` for headless; `orq traces conversation` renders a run as text. | [Setup](modules/00.md), [Coding agents](modules/13.md) |
| 4.15 | Request metadata via `X-ORQ-METADATA-<key>` and `X-ORQ-THREAD-ID` headers, for agents that cannot change the body. | [Tracing](modules/02.md), [Coding agents](modules/13.md) |
| 4.15 | Google GenAI-compatible wire under `/v3/google`: Gemini CLI and the Gen AI SDKs through the gateway. | [Gateway](modules/01.md), [Coding agents](modules/13.md) |
| 4.15 | Span panel splits tokens into input, output and reasoning. | [Tracing](modules/02.md) |
| 4.15 | **Server tools**: `orq:web_search`, `orq:advisor`, `orq:subagent` and others in `tools`, executed by the gateway on Responses and Chat Completions, reported under `usage.server_tool_use`. | [Gateway](modules/01.md), [Advisor and sidekick](modules/15.md) |
| 4.15 | New model `openai/gpt-6-astra`; `deepseek-v4-flash` now also on Inceptron and Nebius. | [Gateway](modules/01.md) |
| 4.15 | **MCP Gateway**: OAuth browser sign-in as the default connection, egress policy and runtime limits, plugins on every tool call. | [MCP Gateway](modules/10.md) |
| 4.15 | MCP Servers are a separate section in the Agent builder, not a tool type. | [Managed agents](modules/08.md), [MCP Gateway](modules/10.md) |
| 4.15 | Python editor for evaluators and tools: completions, inline diagnostics, Ruff formatting. | [Failure analysis and evals](modules/07.md), [Managed agents](modules/08.md) |
| 4.15 | PII detection by region and entity (NL, UK, BE, DE, FR, US identifiers) as a system guardrail. | [Guardrails](modules/04.md) |
| 4.15 | Evaluators skip Agent runs that ended in an error. | [Evals in CI](modules/12.md) |
| 4.15 | **Telemetry API** (Beta): `POST /v3/telemetry/query` replaces the Reporting API; module 14 not yet migrated, still posts to `/v2/reporting`. Alerts on Deployment guardrails. | [Alerts and webhooks](modules/14.md) |
| 4.15 | Workspace Security tab: domain verification, IP allowlist (Enterprise). Custom and AWS Bedrock models price cached tokens. | [Budgets and keys](modules/05.md) |
| 4.15 | Legacy sidebar and the separate Control Tower app retired. Screenshots of the old navigation are out of date. | Screenshots |
| 4.14 | **MCP Portal**: MCP Servers and MCP Gateway in one place. Gateway bundles upstream servers behind `/v3/mcp/<key>`, exposes all, selected or none of each server's tools, logs every call including denied ones. Code Mode vs Direct Mode. | [MCP Gateway](modules/10.md) |
| 4.14 | Guardrail and evaluator indicators on every trace span; time-range selector; search by id. | [Tracing](modules/02.md), [Guardrails](modules/04.md) |
| 4.14 | OpenAI Codex sessions captured as traces; CLI onboarding in the Studio. | [Coding agents](modules/13.md) |
| 4.13 | **Smart Router** page with model bands from an intelligence index, `route_pool` over N candidates, quality / balanced / cost profiles. | [Smart routing](modules/03.md) |
| 4.14 | **Alerts** on Reporting API metrics (cost, latency, errors, guardrails) with triggers and notifiers; **webhooks** for `llm.response` and other workspace events, HMAC-signed. | [Alerts and webhooks](modules/14.md) |
| 4.14 | **Trace automations**: a filter, a sampling rate, and an action, add matching traces to a dataset or to an annotation queue. | [Annotation queues and automations](modules/17.md) |
| 4.13 | **Advisor and Sidekick** tools: an agent consults a second model mid-turn, or delegates a discrete task. Metered separately, own spans. | [Advisor and sidekick](modules/15.md) |
| 4.13 | Guardrail sampling and non-blocking mode for system guardrails; redesigned thread view; span-to-source links; `store: false` on Responses. | [Guardrails](modules/04.md), [Tracing](modules/02.md) |
| 4.12 | **System guardrails**: built-in PII Detection and Secret Detection, fail-closed, monitor mode. PII redaction up to 10x faster. | [Guardrails](modules/04.md) |
| 4.12 | Filter traces by number of messages; configurable tool timeout per agent tool. | [Tracing](modules/02.md), [Managed agents](modules/08.md) |
| 4.11 | **Budgets** as a first-class entity: workspace, project, identity, API key, provider or model scope; cost, token or requests-per-minute limits; alerts; Management Keys. | [Budgets and keys](modules/05.md) |
| 4.11 | **PII redaction plugin**: placeholders before the provider, originals restored on the way back, workspace or request level. | [Guardrails](modules/04.md) |
| 4.11 | Memory Stores UI; Human Review renamed **Annotations** with queues and an API; MCP setup timing as spans; incremental streaming on the router. | [Managed agents](modules/08.md), [Tracing](modules/02.md), [Annotation queues and automations](modules/17.md) |
| 4.10 | Broader framework tracing: LangGraph, Vercel AI SDK, Pydantic AI, Mastra, Agno, Google ADK, Claude Agent SDK. `invoke_model` MCP tool with reasoning options. | [Tracing](modules/02.md) |
| 4.9 | LangGraph graph view next to its trace; global LangChain callback registration. | [Tracing](modules/02.md) |
| 4.6 | **Red teaming** in evaluatorq: OWASP LLM Top 10 and Agentic (ASI) categories, agent-aware attacks, exit-code gating, results as Experiment runs. **Auto Router**. | [Red teaming](modules/16.md), [Evals in CI](modules/12.md) |
| CLI 8.x | `orq launch <agent>` (session-only gateway routing, MCP and skills), `orq connect --local` (permanent wiring per project), `orq traces thread`, `orq traces insights`, `orq doctor`, `orq orqi`. | [Setup](modules/00.md), [Troubleshooting with orqi](modules/06.md), [Coding agents](modules/13.md) |
| orqi | Terminal helper agent with 43 orq.ai MCP tools, the orq.ai skills plus seven of its own (`investigate-root-cause`, `debug-conversation`, `workspace-health-check`, `optimize-cost`, `setup-guardrails`, `manage-knowledge-base`, `platform-guide`). Alpha. | [Troubleshooting with orqi](modules/06.md), [Evals in CI](modules/12.md) |

!!! note "Naming drift worth knowing"
    On Agents the delegation tools are `advisor` and `sidekick`. On the gateway's server tools they are `orq:advisor` and `orq:subagent`; `orq:sidekick` is a legacy alias. The MCP Tool type on agents is retired: MCP connections are managed in the MCP Portal.
