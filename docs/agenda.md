# Agenda

Two half-days, about 3.5 hours each with breaks. Times are targets, not a script. The [instructor notes](instructor/index.md) say what to cut when a room runs slow.

## Day 1 · Control plane

| Time | Module | You leave with |
|---|---|---|
| 0:00 | [00 Setup](modules/00.md) | a green `orq doctor` and one trace |
| 0:20 | [01 Gateway](modules/01.md) | fallbacks, retry, cache, load balancing as request fields |
| 0:45 | [02 Tracing](modules/02.md) | agent, tool and LLM spans with identity and thread |
| 1:15 | break | |
| 1:25 | [03 Smart routing](modules/03.md) | a smart router and a routing rule |
| 1:45 | [04 Guardrails](modules/04.md) | PII redaction and a blocking guardrail rule |
| 2:10 | [05 Budgets and keys](modules/05.md) | a per-identity budget that rejects the third call |
| 2:25 | break | |
| 2:35 | [06 Troubleshooting with orqi](modules/06.md) | a root cause found by an agent, not by you |
| 2:50 | [07 Failure analysis to experiments](modules/07.md) | a failure taxonomy, a judge, an experiment |
| 3:30 | close | |

## Day 2 · Agents

| Time | Module | You leave with |
|---|---|---|
| 0:00 | [08 Managed agents](modules/08.md) | the refund agent hosted by orq, with memory |
| 0:40 | [09 Knowledge base and RAG](modules/09.md) | the policy as a knowledge base, hybrid search with rerank |
| 1:15 | break | |
| 1:25 | [10 MCP servers and gateway](modules/10.md) | one governed MCP endpoint that exposes two of three tools |
| 1:55 | [11 Simulation and red teaming](modules/11.md) | a vulnerable agent that fails, a fixed one that passes |
| 2:35 | break | |
| 2:45 | [12 Evals and agents in CI](modules/12.md) | a GitHub Actions gate and a nightly triage agent |
| 3:20 | [13 Coding agents and wrap-up](modules/13.md) | your coding agent wired to orq, applied to your own repo |
| 3:45 | close | |

## Three-hour live session

The [slide deck](https://github.com/orq-ai/orq-workshop/tree/main/slides) is the spine for a single 3-hour session. It opens with a priority vote and picks four or five blocks from the list above.
