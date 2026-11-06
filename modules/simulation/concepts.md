# Simulation concepts

Read before this module. Why simulated conversations complement a fixed dataset, and the control case, are on the [Evaluate](https://orq-ai.github.io/orq-workshop/evaluate/) stage page. This page names the pieces.

## Three models, one transcript

A **user simulator** plays a persona with a goal. The **target** responds. After each target turn a **judge** audits the transcript against the scenario's criteria and decides whether to continue; `max_turns` caps it otherwise. The starter uses `JUDGE_MODEL` for simulator and judge, through the orq.ai router. `save=True` keeps conversations for `eq dashboard`; results also land in a Studio Experiment.

```python
results = await simulate(
    target=local_agent("fixed"),       # the agent under test
    personas=PERSONAS,
    scenarios=SCENARIOS,
    max_turns=4,
    llm_config=SIM_LLM,                # simulator and judge, through the router
    save=True,
)
```

![Diagram: the simulation loop: user simulator, target, transcript up to max_turns, judge writing one row per conversation into an Experiment run.](assets/simulation-loop.png)

A target maps a transcript to a reply: an async callable, `"agent:<key>"` for a managed agent, or an `AgentTarget` subclass.

## Designing a case

| Piece | What you define |
|---|---|
| **Persona** | Patience, assertiveness, politeness, style, as traits from 0 to 1. |
| **Scenario** | The goal, the facts the customer knows (`context`) and the starting emotion. |
| **Criteria** | Per scenario: observable evidence the judge checks, as `must_happen` or `must_not_happen`. |

`simulate()` takes the cross product of personas and scenarios; criteria are not a dimension. **Goal achieved** and **rules broken** are separate verdicts. A criterion such as `Criterion(description="Agent states the refunded amount as EUR 24.99", type="must_happen")` is satisfied once the behavior occurs on any turn; `must_not_happen` is violated once it occurs, and a later correction does not erase it. These are observations, not guardrails: a violation can stop the run but cannot undo an action.

## Why the conversation stopped

| `terminated_by` | Meaning |
|---|---|
| `judge` | Success, a violation, or an unreachable goal. Not a pass by itself. |
| `max_turns` | Turn budget ran out. The score estimates progress, not a verdict. |
| `error` or `timeout` | Did not finish. Treat missing verdicts as unknown. |

An empty `rules_broken` list does not replace a regression test. The judge reads transcript text only: tool calls inside a callable target are invisible to it, and it knows no refund policy beyond the criteria.

Next: [run the simulation](https://orq-ai.github.io/orq-workshop/modules/simulation/).

## Official docs

- [Agent simulations](https://docs.orq.ai/ai-studio/optimize/agent-simulations)
- [Simulation cookbook](https://docs.orq.ai/ai-studio/cookbooks/evaluation-safety/agent-simulations)
- [Evaluatorq](https://docs.orq.ai/ai-studio/cookbooks/evaluation-safety/evaluator-q)
