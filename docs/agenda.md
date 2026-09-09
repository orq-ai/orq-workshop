# Agenda

Two tracks. **AI Gateway** puts the control plane under your hands: every call goes through orq, and you decide what it may cost, route to, redact and block. **Managed Agents** hands the agent itself to orq and then attacks it: knowledge, tools, simulation, red teaming, CI.

The order below is the default, not a script. Modules build on each other, but `make seed` creates every prerequisite entity, so a room can start anywhere or skip a module. Take a break between any two modules. The [instructor notes](instructor/index.md) say what to cut when a room runs slow.

## AI Gateway track

| Module | You leave with |
|---|---|
| [00 Setup](modules/00.md) | a green `orq doctor` and one trace |
| [01 Gateway](modules/01.md) | fallbacks, retry, cache, load balancing as request fields |
| [02 Tracing](modules/02.md) | agent, tool and LLM spans with identity and thread |
| [03 Smart routing](modules/03.md) | a smart router and a routing rule |
| [04 Guardrails](modules/04.md) | PII redaction and a blocking guardrail rule |
| [05 Budgets and keys](modules/05.md) | a per-identity budget that rejects the third call |
| [06 Troubleshooting with orqi](modules/06.md) | a root cause found by an agent, not by you |
| [07 Failure analysis to experiments](modules/07.md) | a failure taxonomy, a judge, an experiment |

## Managed Agents track

| Module | You leave with |
|---|---|
| [08 Managed agents](modules/08.md) | the refund agent hosted by orq, with memory |
| [09 Knowledge base and RAG](modules/09.md) | the policy as a knowledge base, hybrid search with rerank |
| [10 MCP servers and gateway](modules/10.md) | one governed MCP endpoint that exposes two of three tools |
| [11 Simulation and red teaming](modules/11.md) | a vulnerable agent that fails, a fixed one that passes |
| [12 Evals and agents in CI](modules/12.md) | a GitHub Actions gate and a nightly triage agent |
| [13 Coding agents and wrap-up](modules/13.md) | your coding agent wired to orq, applied to your own repo |

## Live session

The [slide deck](https://github.com/orq-ai/orq-workshop/tree/main/slides) is the spine for a single session. It opens with a priority vote and picks four or five blocks from the modules above, so the room decides the order.
