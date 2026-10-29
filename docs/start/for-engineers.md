# For engineers

The core path takes one sample app, a customer-support refund agent, around the loop once: about four hours, seven modules and a wrap-up. Every step runs with a participant key; nothing on this path needs admin rights or a tunnel. Each module says what it starts from, what it leaves behind, and hands you to the next.

Optional on every path: wire your own [coding agent](../modules/coding-agents.md) through orq.ai, so the "With your coding agent" prompt in each module has somewhere to go.

<div class="steps" markdown>

1. [Setup](../modules/setup.md) (20 min): a green `orq doctor` and one trace.
2. [Gateway](../modules/gateway.md) (25 min): fallbacks, retry, cache, load balancing as request fields.
3. [Tracing](../modules/tracing.md) (30 min): agent, tool and LLM spans with identity and thread.
4. [Managed agents](../modules/managed-agents.md) (40 min): the refund agent hosted by orq, with memory.
5. [Failure analysis to experiments](../modules/failure-analysis.md) (40 min): a failure taxonomy, a judge, an experiment.
6. [Agent simulation](../modules/simulation.md) (30 min): four simulation runs as Experiments, and the row where an empty answer passed.
7. [Evals and agents in CI](../modules/evals-in-ci.md) (35 min): a GitHub Actions gate and a nightly triage agent.
8. [Wrap-up](wrap-up.md): apply the loop to your own repo.

</div>

Total: about 220 minutes of hands-on work, plus breaks.

## What each module needs

Every core-path module runs with the participant key from Setup. The electives below need more; their restricted steps are marked **Instructor demo** in the module, so a room without that access can still follow.

| Module | Needs | Restricted part |
|---|---|---|
| [Smart routing](../modules/smart-routing.md) | admin key | the routing-rule steps |
| [Guardrails](../modules/guardrails.md) | admin key | the guardrail-rule step |
| [Budgets and keys](../modules/budgets-and-keys.md) | Management Key | the whole module |
| [MCP servers and gateway](../modules/mcp-gateway.md) | workspace-wide key | creating the MCP server and gateway |
| [Knowledge base and RAG](../modules/knowledge-base.md) | public tunnel | the external knowledge base step only |
| [Alerts and webhooks](../modules/alerts-and-webhooks.md) | public tunnel | the webhook receiver step only |

Everything else needs only the participant key and `make seed-workspace`.

## After the core path

[Already on orq.ai](already-on-orq.md) lists the electives by stage. Pick by the stage you are weakest on, not by order.
