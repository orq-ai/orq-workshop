# Agenda

Six sections, the same six as the tabs of this site, in the order a team usually needs them. **Setup** installs the three harnesses you will work from: the orq.ai CLI, your coding agent, and orqi. **AI Gateway** puts the control plane under your hands: every call goes through orq.ai, and you decide what it may cost, route to, redact and block, and who pays for it. **AI Observability** turns the traces that produces into evidence, with alerts and webhooks that push them to you and a review queue that collects what a human should read. **Agents** moves the agent from your loop to a framework's to orq.ai's, then adds delegation. **RAG and Retrieval** gives it knowledge. **Evaluation** attacks and measures it: simulation, failure analysis, evaluators, CI and red teaming.

Modules build on each other, but `make seed` creates every prerequisite entity, so a room can start anywhere or skip a module. Take a break between any two modules. The instructor notes in the repo (`instructor/`) say what to cut when a room runs slow.

## Setup

| Module | You leave with |
|---|---|
| [Setup](modules/00.md) | a green `orq doctor` and one trace |
| [Coding agents](modules/13.md) | your coding agent wired to orq, applied to your own repo |
| [orqi harness](setup/orqi.md) | orqi installed, signed in with the repo key, and a header line that shows `43 tools` |
| [Troubleshooting with orqi](modules/06.md) | a root cause found by an agent, not by you |

## AI Gateway

| Module | You leave with |
|---|---|
| [Gateway](modules/01.md) | fallbacks, retry, cache, load balancing as request fields |
| [Smart routing](modules/03.md) | a smart router and a routing rule |
| [Guardrails](modules/04.md) | PII redaction and a blocking guardrail rule |
| [Budgets and keys](modules/05.md) | a per-identity budget that rejects the third call, a Management Key, and the [Terraform](reference/terraform.md) provider that would declare both |
| [MCP servers and gateway](modules/10.md) | one governed MCP endpoint that exposes two of three tools |

## AI Observability

| Module | You leave with |
|---|---|
| [Tracing](modules/02.md) | agent, tool and LLM spans with identity and thread |
| [Alerts and webhooks](modules/14.md) | a cost alert that fired on a burst you caused, and orq events arriving signed at a receiver you run |
| [Annotation queues and automations](modules/17.md) | a review queue an automation fills, reviewed by API, and the reviewed traces promoted to a dataset |

## Agents

| Module | You leave with |
|---|---|
| [Managed agents](modules/08.md) | the refund agent hosted by orq, with memory |
| [Advisor and sidekick](modules/15.md) | a cheap agent that pays for a strong model only at the step that needs it, and the cost split to prove it |

## RAG and Retrieval

| Module | You leave with |
|---|---|
| [Knowledge base and RAG](modules/09.md) | the policy as a knowledge base, hybrid search with rerank |

## Evaluation

| Module | You leave with |
|---|---|
| [Evals and agents in CI](modules/12.md) | a GitHub Actions gate and a nightly triage agent |
| [Agent simulation](modules/11.md) | four simulation runs as Experiments, and the row where an empty answer passed |
| [Trace insights](modules/18.md) | failure clusters named from your own simulated conversations, and the Pass/Fail sentence that becomes an evaluator |
| [Red teaming](modules/16.md) | a vulnerable agent that fails and a fixed one that passes the same OWASP attack set, and a CLI gate that exits 0 or 1 |
| [Failure analysis to experiments](modules/07.md) | a failure taxonomy, a judge, an experiment |

## Live session

A slide deck for a single session lives in [`slides/`](https://github.com/orq-ai/orq-workshop/tree/main/slides). It runs a few fixed blocks; the other modules sit in the appendix, one slide each, and can be swapped in. `sessions/workshop/run-of-show.md` has the timing.
