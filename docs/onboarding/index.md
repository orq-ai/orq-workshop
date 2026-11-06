# Onboarding

How orq.ai comes into a company in the first week: team leaders first, so they know which problem each part of orq.ai answers for them; the platform owner next, so the workspace is ready; then the engineers, on the refund agent and on their own app. The [Academy](../academy/index.md) and the [Workshop](../workshop/index.md) are the material; this section is how a week runs on them.

!!! note "Outline"
    The full week (run-of-show, flex catalogue, workspace checklist, readout template) is being written. The shape below is fixed.

## Week one

A fixed spine that needs nothing from the client, two flex slots with defaults, and an optional "on your app" exercise at the end of each engineering block. Engineers work half-days.

| Block | Who | Length | Content |
|---|---|---|---|
| L1 · The loop, at orq.ai | team leaders | 2 h | the loop, a stage walk with one Studio clip per stage, the symptom finder, owners per stage |
| P1 · Workspace ready | platform owner and instructor | 90 min | projects, providers and models, keys and budgets, SSO and roles, a seeded sandbox project, one participant key passing setup |
| L2 · Leader deep dive (flex) | team leaders | 1 h | one deep dive; default: Governance |
| E1 · Route and trace | engineers | 3 h | [Setup](../modules/setup.md), [Gateway](../modules/gateway.md), [Tracing](../modules/tracing.md); on your app |
| E2 · Build and find failures | engineers | 3 h | [Managed agents](../modules/managed-agents.md), generated traffic, [Failure analysis](../modules/failure-analysis.md); on your app |
| E3 · Evaluate, plus one pack (flex) | engineers | 2 h + 1 h | [Evaluators and experiments](../modules/evaluators-and-experiments.md), [Agent simulation](../modules/simulation.md); on your app; one engineer pack, default: Protect |
| E4 · Gate it | engineers | 2 h | [Evals and agents in CI](../modules/evals-in-ci.md), [Wrap-up](../workshop/wrap-up.md); prepare the readout |
| R · Readout | everyone | 1 h | each team shows a trace, a failure, an evaluator and the gate that catches it; leaders score the checklists; the next stage, its owner, a date for the 30-day check |

Over five days: L1 and P1, then L2 and E1, then E2, then E3, then E4 and the readout. Squeezed to two days: L1, P1 and E1, then E2, E3, E4 and the readout, without the flex slots and the "on your app" exercises.

## Engineer packs

One hour each, built from existing modules. Each answers a symptom from the Academy's symptom finder.

| Pack | Modules |
|---|---|
| Protect (default) | [Guardrails](../modules/guardrails.md), [Smart routing](../modules/smart-routing.md), [Budgets and keys](../modules/budgets-and-keys.md) as an instructor demo |
| Ground | [Knowledge base and RAG](../modules/knowledge-base.md), [MCP servers and gateway](../modules/mcp-gateway.md) |
| Harden | [Red teaming](../modules/red-teaming.md), [Trace insights](../modules/trace-insights.md) |
| Operate | [Alerts and webhooks](../modules/alerts-and-webhooks.md), [Annotation queues and automations](../modules/annotation-queues.md) |
| Delegate | [Advisor and sidekick](../modules/advisor-and-sidekick.md), [Coding agents](../modules/coding-agents.md) |

## Past sessions

- [TechDays 15 Oct](../sessions/techdays-2026.md)
