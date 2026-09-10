# Glossary

**AI Gateway / router.** The OpenAI-compatible endpoint at `/v3/router`. Any OpenAI SDK, framework or coding agent points its base URL there and gets tracing, fallbacks, cache, routing rules, guardrails and budgets without code changes. Anthropic-compatible at `/v3/anthropic`. [Docs](https://docs.orq.ai/docs/ai-gateway/features/openai-compatible-api)

**Smart Router.** A workspace entity with a pool of 2 to 50 models and a profile (quality, balanced, cost). Called like a model: `<workspace>@orq/<key>`. Picks a model per request from an intelligence index. [Docs](https://docs.orq.ai/docs/ai-gateway/smart-router)

**Routing rule.** A CEL expression over request attributes that replaces the requested model, fallbacks or load balancer at the gateway. Applies to any caller. [Docs](https://docs.orq.ai/docs/ai-gateway/configuration/routing-rules)

**Guardrail.** An evaluator (LLM or Python) with a pass condition, run on input or output of a gateway call or agent turn. A failed guardrail blocks with HTTP 422. **System guardrails** are the built-in PII Detection and Secret Detection. **Guardrail rule** attaches guardrails and plugins to matching requests. [Docs](https://docs.orq.ai/docs/ai-gateway/configuration/guardrails)

**PII redaction plugin.** Request-scoped plugin that swaps detected PII for placeholders before the provider sees the text and restores the originals in the response. Different from the PII Detection guardrail, which blocks instead of rewriting. [Docs](https://docs.orq.ai/docs/ai-gateway/features/plugins/pii-redaction)

**Budget.** Cost, token or requests-per-minute limit on a workspace, project, identity, API key, provider or model. Managed with a Management Key. [Docs](https://docs.orq.ai/docs/ai-gateway/budgets)

**Identity.** The end user behind a request. Attach `orq.identity.id` on a call so traces, annotations and budgets can be scoped to a person. [Docs](https://docs.orq.ai/docs/ai-studio/observability/identities)

**Thread.** A conversation id. Attach `orq.thread.id` so multi-turn traces group into one thread view. [Docs](https://docs.orq.ai/docs/ai-gateway/thread-management)

**Managed agent.** An agent hosted by orq: instructions, model, tools (function, HTTP, built-in, MCP), knowledge bases, memory stores, versions and environments. Invoked through the Responses API as `model="agent/<key>"`. [Docs](https://docs.orq.ai/docs/ai-studio/ai-engineering/build-agents)

**Advisor / Sidekick.** Built-in agent tools. Advisor: ask a second model for guidance on the conversation so far. Sidekick: delegate a discrete task with its own instructions and get only the result. On the gateway's server tools these are `orq:advisor` and `orq:subagent`. [Docs](https://docs.orq.ai/docs/ai-studio/cookbooks/common-architecture/advisor-and-sidekick)

**Knowledge base.** Chunked documents with embeddings and hybrid search plus rerank and optional agentic RAG. **External knowledge base** is your own search endpoint that implements the `/search` contract. [Docs](https://docs.orq.ai/docs/ai-studio/ai-engineering/knowledge-bases)

**Orq MCP server.** `https://my.orq.ai/v2/mcp`. The MCP server coding agents connect to for workspace administration: agents, datasets, evaluators, experiments, traces, docs search. Wired by `orq launch` and `orq connect mcp`. [Docs](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-mcp)

**MCP Portal.** The area of the AI Gateway where upstream **MCP Servers** are registered (URL, auth, discovered tools) and **MCP Gateways** bundle them. [Docs](https://docs.orq.ai/docs/ai-gateway/mcp-portal/mcp-servers)

**MCP Gateway.** One client-facing MCP endpoint at `/v3/mcp/<key>` fronting several MCP Servers, with per-server tool exposure, read-only filters, naming rules and an audit log of every call. Consumed by coding agents and managed agents alike. [Docs](https://docs.orq.ai/docs/ai-gateway/mcp-portal/mcp-gateways)

**orq CLI.** `orq`. Signs in, mints keys, manages every entity, and wires coding agents: `orq setup`, `orq connect`, `orq launch`, `orq doctor`. [Docs](https://docs.orq.ai/reference/cli)

**Orq Skills.** Agent-skills-standard workflows (`build-agent`, `analyze-trace-failures`, `build-evaluator`, `run-experiment`, `red-team`, `simulate-agent`, ...) shipped inside the CLI binary, sourced from `orq-ai/assistant-plugins`. Not the same as **Skills** the platform entity (reusable prompt snippets referenced as `{{skill.key}}`). [Docs](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-skills)

**orqi.** The orq terminal helper agent. Embeds the pi coding agent, routes through the gateway, ships the orq MCP tools, the orq skills and seven troubleshooting skills of its own. Alpha.

**evaluatorq.** Python and TypeScript evaluation framework from orq. Runs jobs over datasets with evaluators, exits non-zero on failure, uploads results as Experiment runs. Also does agent simulation and red teaming. [Docs](https://docs.orq.ai/docs/ai-studio/cookbooks/evaluation-safety/evaluator-q)
