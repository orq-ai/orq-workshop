# Agenda

Three sections, the same three as [docs.orq.ai](https://docs.orq.ai), after a **Setup** block that installs the three harnesses you will work from: the orq CLI, your coding agent, and orqi. **AI Gateway** puts the control plane under your hands: every call goes through orq, and you decide what it may cost, route to, redact and block, and who pays for it. **AI Observability** turns the traces that produces into evidence: threads, spans, a failure taxonomy and evaluators built from those traces and an experiment that scores the fix, alerts and webhooks that push them to you, and a review queue that collects what a human should read. **Managed Agents** hands the agent to orq and attacks it: knowledge, tools, simulation, CI, delegation, red teaming.

Module numbers are the build order (`make m01` … `make m17`), sections are the topic, so the numbers below are not contiguous. Modules build on each other, but `make seed` creates every prerequisite entity, so a room can start anywhere or skip a module. Take a break between any two modules. The instructor notes in the repo (`instructor/`) say what to cut when a room runs slow.

## Setup

| Module | You leave with |
|---|---|
| [00 Setup](modules/00.md) | a green `orq doctor` and one trace |
| [13 Coding agents and wrap-up](modules/13.md) | your coding agent wired to orq, applied to your own repo |
| [orqi harness](setup/orqi.md) | orqi installed, signed in with the repo key, and a header line that shows `43 tools` |
| [06 Troubleshooting with orqi](modules/06.md) | a root cause found by an agent, not by you |

## AI Gateway

| Module | You leave with |
|---|---|
| [01 Gateway](modules/01.md) | fallbacks, retry, cache, load balancing as request fields |
| [03 Smart routing](modules/03.md) | a smart router and a routing rule |
| [04 Guardrails](modules/04.md) | PII redaction and a blocking guardrail rule |
| [05 Budgets and keys](modules/05.md) | a per-identity budget that rejects the third call, a Management Key, and the [Terraform](reference/terraform.md) provider that would declare both |

## AI Observability

| Module | You leave with |
|---|---|
| [02 Tracing](modules/02.md) | agent, tool and LLM spans with identity and thread |
| [07 Failure analysis to experiments](modules/07.md) | a failure taxonomy, a judge, an experiment |
| [14 Alerts and webhooks](modules/14.md) | a cost alert that fired on a burst you caused, and orq events arriving signed at a receiver you run |
| [17 Annotation queues and automations](modules/17.md) | a review queue an automation fills, reviewed by API, and the reviewed traces promoted to a dataset |

## Managed Agents

| Module | You leave with |
|---|---|
| [08 Managed agents](modules/08.md) | the refund agent hosted by orq, with memory |
| [09 Knowledge base and RAG](modules/09.md) | the policy as a knowledge base, hybrid search with rerank |
| [10 MCP servers and gateway](modules/10.md) | one governed MCP endpoint that exposes two of three tools |
| [11 Agent simulation](modules/11.md) | four simulation runs as Experiments, and the row where an empty answer passed |
| [12 Evals and agents in CI](modules/12.md) | a GitHub Actions gate and a nightly triage agent |
| [15 Advisor and sidekick](modules/15.md) | a cheap agent that pays for a strong model only at the step that needs it, and the cost split to prove it |
| [16 Red teaming](modules/16.md) | a vulnerable agent that fails and a fixed one that passes the same OWASP attack set, and a CLI gate that exits 0 or 1 |

## Live session

The [slide deck](https://github.com/orq-ai/orq-workshop/tree/main/slides) is the spine for a single session. It runs four fixed blocks chosen from what the client asked for in writing: own your agent, managed agents, knowledge base and RAG, and MCP servers with the MCP Gateway. The other modules sit in the appendix, one slide each, and can be swapped in on request; `slides/facilitator.md` has the timing.
