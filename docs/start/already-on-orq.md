# Already on orq.ai

You have an agent on orq.ai, or an app behind the gateway, and you know the basics. Skip the core path and take the electives for the stage you want to get better at. Each module starts from `make seed-workspace`, so none of them needs the others, unless its Starting point says so.

## Build

[Read the concept page first](../build/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Managed agents](../modules/managed-agents.md) | the refund agent hosted by orq, with memory | participant key |
| [Knowledge base and RAG](../modules/knowledge-base.md) | the policy as a knowledge base, hybrid search with rerank | public tunnel |
| [MCP servers and gateway](../modules/mcp-gateway.md) | one governed MCP endpoint that exposes two of three tools | workspace-wide key |
| [Advisor and sidekick](../modules/advisor-and-sidekick.md) | a cheap agent that pays for a strong model only at the step that needs it, and the cost split to prove it | participant key |

## Route and protect

[Read the concept page first](../route/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Gateway](../modules/gateway.md) | fallbacks, retry, cache, load balancing as request fields | participant key |
| [Smart routing](../modules/smart-routing.md) | a smart router and a routing rule | admin key |
| [Guardrails](../modules/guardrails.md) | PII redaction and a blocking guardrail rule | admin key |
| [Budgets and keys](../modules/budgets-and-keys.md) | a per-identity budget that rejects the third call, a Management Key, and the [Terraform](../reference/terraform.md) provider that would declare both | Management Key |

## Trace

[Read the concept page first](../trace/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Tracing](../modules/tracing.md) | agent, tool and LLM spans with identity and thread | participant key |

## Find failures

[Read the concept page first](../find-failures/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Failure analysis to experiments](../modules/failure-analysis.md) | a failure taxonomy, a judge, an experiment | participant key |
| [Trace insights](../modules/trace-insights.md) | failure clusters named from your own simulated conversations, and the Pass/Fail sentence that becomes an evaluator | participant key |
| [Annotation queues and automations](../modules/annotation-queues.md) | a review queue an automation fills, reviewed by API, and the reviewed traces promoted to a dataset | participant key |

## Evaluate

[Read the concept page first](../evaluate/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Agent simulation](../modules/simulation.md) | four simulation runs as Experiments, and the row where an empty answer passed | participant key |
| [Red teaming](../modules/red-teaming.md) | a vulnerable agent that fails and a fixed one that passes the same OWASP attack set, and a CLI gate that exits 0 or 1 | participant key |

## Gate and monitor

[Read the concept page first](../gate/index.md).

| Module | You leave with | Needs |
|---|---|---|
| [Evals and agents in CI](../modules/evals-in-ci.md) | a GitHub Actions gate and a nightly triage agent | participant key |
| [Alerts and webhooks](../modules/alerts-and-webhooks.md) | a cost alert that fired on a burst you caused, and orq events arriving signed at a receiver you run | public tunnel |

## Harnesses

| Module | You leave with | Needs |
|---|---|---|
| [Coding agents](../modules/coding-agents.md) | your coding agent wired to orq, applied to your own repo | participant key |
| [Troubleshooting with orqi](../modules/orqi.md) | a root cause found by an agent, not by you | participant key |

## Keep it running

The [wrap-up](wrap-up.md) is the same loop applied to your own repository, with the orq.ai skills installed in your coding agent so the next change goes around it too.
