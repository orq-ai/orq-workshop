# The core path

One agent, one loop, about four hours. Every step below runs with a participant key; nothing needs admin rights or a tunnel. Each module ends with a **Done when** list and hands you the state the next one starts from. `make seed-workspace` creates every entity the modules expect, so you can also jump in anywhere.

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

## Electives by stage

The rest of the modules, grouped by the stage of the loop they belong to. Take them in any order after their Starting point is met.

## Build

| Module | You leave with |
|---|---|
| [Managed agents](../modules/managed-agents.md) | the refund agent hosted by orq, with memory |
| [Knowledge base and RAG](../modules/knowledge-base.md) | the policy as a knowledge base, hybrid search with rerank |
| [MCP servers and gateway](../modules/mcp-gateway.md) | one governed MCP endpoint that exposes two of three tools |
| [Advisor and sidekick](../modules/advisor-and-sidekick.md) | a cheap agent that pays for a strong model only at the step that needs it, and the cost split to prove it |

## Route and protect

| Module | You leave with |
|---|---|
| [Gateway](../modules/gateway.md) | fallbacks, retry, cache, load balancing as request fields |
| [Smart routing](../modules/smart-routing.md) | a smart router and a routing rule |
| [Guardrails](../modules/guardrails.md) | PII redaction and a blocking guardrail rule |
| [Budgets and keys](../modules/budgets-and-keys.md) | a per-identity budget that rejects the third call, a Management Key, and the [Terraform](../reference/terraform.md) provider that would declare both |

## Trace

| Module | You leave with |
|---|---|
| [Tracing](../modules/tracing.md) | agent, tool and LLM spans with identity and thread |

## Find failures

| Module | You leave with |
|---|---|
| [Failure analysis to experiments](../modules/failure-analysis.md) | a failure taxonomy, a judge, an experiment |
| [Trace insights](../modules/trace-insights.md) | failure clusters named from your own simulated conversations, and the Pass/Fail sentence that becomes an evaluator |
| [Annotation queues and automations](../modules/annotation-queues.md) | a review queue an automation fills, reviewed by API, and the reviewed traces promoted to a dataset |

## Evaluate

| Module | You leave with |
|---|---|
| [Agent simulation](../modules/simulation.md) | four simulation runs as Experiments, and the row where an empty answer passed |
| [Red teaming](../modules/red-teaming.md) | a vulnerable agent that fails and a fixed one that passes the same OWASP attack set, and a CLI gate that exits 0 or 1 |

## Gate and monitor

| Module | You leave with |
|---|---|
| [Evals and agents in CI](../modules/evals-in-ci.md) | a GitHub Actions gate and a nightly triage agent |
| [Alerts and webhooks](../modules/alerts-and-webhooks.md) | a cost alert that fired on a burst you caused, and orq events arriving signed at a receiver you run |

## Harnesses

| Module | You leave with |
|---|---|
| [Coding agents](../modules/coding-agents.md) | your coding agent wired to orq, applied to your own repo |
| [orqi harness](../start/orqi.md) | orqi installed, signed in with the repo key, and a header line that shows `43 tools` |
| [Troubleshooting with orqi](../modules/orqi.md) | a root cause found by an agent, not by you |

## Live sessions

A slide deck for a single session lives in [`slides/`](https://github.com/orq-ai/orq-workshop/tree/main/slides); `sessions/<name>/run-of-show.md` has the timing of each past session.
