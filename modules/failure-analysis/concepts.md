# Concepts

Read before this module. Why error analysis comes before evaluators, and how a taxonomy is built, is on the [Find failures](https://orq-ai.github.io/orq-workshop/find-failures/) stage page. This page is what the module's own scorers and gate look like.

## The refund agent's scorers

Every scorer is binary and maps to one failure mode of the taxonomy. Code checks a fact; a judge reads text:

| Scorer | Kind | Passes when |
|---|---|---|
| `decision_matches` | code | `issue_refund` was called if and only if the row expects a refund |
| `no_pii_leak` | code | the answer repeats no email address or phone number |
| `policy_judge` | LLM judge | the orq.ai evaluator `ws-refund-policy-judge` says the answer follows policy |

```python
# evals/scorers.py: one scorer, one binary question
async def decision_matches(params):
    output = _out(params)
    expected_refund = params["data"].inputs.get("expected_decision") == "refund"
    refund_called = "issue_refund" in (output.get("tool_calls") or [])
    passed = refund_called == expected_refund
    return EvaluationResult(value=passed, pass_=passed, explanation=...)
```

`decision_matches` reads which tools were called, not what they answered. The judge reads the customer message, the answer and the row's reference, not the tool calls. Run both and read the per-row explanations when they disagree.

![Diagram: the error analysis loop. Traces are read as individual observations, grouped into named failure modes, and turned into binary scorers around a shared failure taxonomy.](assets/error-analysis-loop.png)

## The gate

```python
# evals/regression.py
THRESHOLDS = {"decision_matches": 0.80, "no_pii_leak": 1.00, "policy_judge": 0.70}
failed = [scorer for scorer, threshold in THRESHOLDS.items()
          if scores.get(scorer, 0.0) < threshold]
return 1 if failed else 0
```

The evaluatorq call has three separate layers: **data** supplies rows (`app/data/dataset.jsonl`), a **job** runs the agent on one row and returns a stable output (`answer`, `tool_calls`, `trace_id`), and **evaluators** score that output. Replace any one without rewriting the other two. [Evals and agents in CI](https://orq-ai.github.io/orq-workshop/modules/evals-in-ci/) wires the same command into a pull request.

## Soft fix, hard proof

A prompt fix lowers the odds of a bad choice; it does not make one impossible. The refund tool already enforces ownership, the EUR 500 limit and the 30-day window. Prompts shape likely behavior, tools enforce deterministic policy, and evaluators measure both the answer and the action trail. Do not ask one layer to prove itself.

## Official docs

- [Datasets](https://docs.orq.ai/ai-studio/optimize/datasets)
- [Evaluators](https://docs.orq.ai/ai-studio/optimize/evaluators)
- [Experiments](https://docs.orq.ai/ai-studio/optimize/experiments)
- [Evaluatorq](https://docs.orq.ai/ai-studio/cookbooks/evaluation-safety/evaluator-q)
