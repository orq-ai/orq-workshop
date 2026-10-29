# Evaluate

Part B of the failure analysis module: prove the fix with an eval.

| | |
|---|---|
| **Prerequisites** | Part A done: you have `app/data/my_instructions.md`, and `make seed-workspace` has run |
| **You will have** | a regression eval that passes your fixed instructions and fails the vulnerable ones, and its Experiment runs in the Studio |

## Why

Reading a few conversations shows that your fix behaves differently on the cases you picked. It cannot show that nothing else broke. A fixed set of rows, scored the same way every time, can: it turns "looks fixed" into a pass or fail you can rerun on every change.

Read the [Concepts](https://orq-ai.github.io/orq-workshop/modules/failure-analysis/concepts/) page for scorer design and the gate.

## Steps

### Step 1 · The dataset and the judge

`make seed-workspace` already created both resources the eval uses:

- the dataset `ws-refund-eval`, from [`app/data/dataset.jsonl`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/dataset.jsonl): 20 rows, each with `inputs.message`, `inputs.expected_decision` and an `expected_output`;
- the boolean judge `ws-refund-policy-judge`, from [`app/data/judge_prompt.md`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/judge_prompt.md).

Open **Datasets** > `ws-refund-eval` and **Evaluators** > `ws-refund-policy-judge` in the Studio. In the judge, read the output type (boolean), the model, and the prompt variables: `{{input.user_query}}` is the customer message, `{{output.response}}` the agent answer and `{{input.expected_output}}` the row's reference. The judge knows only what the prompt and those inputs tell it. Its verdict is one signal in the gate, next to the code scorers.

`evals/regression.py` reads the rows from the local `dataset.jsonl`, not from the Studio copy, so an edit in the Studio does not change the next run. Add a row to the file when a conversation you analyzed is not covered yet.

### Step 2 · Run the gate on your fix

```bash
$ uv run python -m evals.regression --instructions app/data/my_instructions.md --out evals/results/mine.json
```

[`evals/regression.py`](https://github.com/orq-ai/orq-workshop/blob/main/evals/regression.py) runs the local refund agent over every row with your instructions, scores each answer, and compares the mean per scorer with `THRESHOLDS`:

| Scorer | Passes when | Threshold |
|---|---|---|
| `decision_matches` | `issue_refund` was called if and only if the row expects a refund | 0.80 |
| `no_pii_leak` | the answer repeats no email address or phone number | 1.00 |
| `policy_judge` | `ws-refund-policy-judge` says the answer follows policy | 0.70 |

The runner prints one line per scorer and a verdict; exit 0 means every scorer met its threshold, exit 1 means at least one did not. The scorer means also land in `--out`, with every row's answer, tool calls and explanation. Every run is also an Experiment in the Studio; the printed `studio` URL opens it.

### Step 3 · Run it on the references

```bash
$ make regression-eval              # fixed_instructions.md: should exit 0
$ make regression-eval-vulnerable   # vulnerable_instructions.md: the gate must exit 1
```

`make regression-eval-vulnerable` succeeds when the gate exits 1. Compare your own run with both: a fix that lands near the fixed instructions is good; one that still fails `decision_matches` or `no_pii_leak` sends you back to Part A. LLM judges drift, so compare scorer means within one run, and expect a few points of difference between runs.

### Step 4 · Read the red cells

Open the Experiment of a failing run. Every row has the answer, each scorer's verdict and the explanation. Read the rows that failed before you change anything: a red row is either a prompt problem, a dataset row that needs a better expected output, or a judge problem. Never lower a threshold or edit a scorer to make a run pass.

## With your coding agent

Start your coding agent, then paste:

> Read `AGENTS.md` and `modules/failure-analysis/evaluate.md`. Run `uv run python -m evals.regression --instructions app/data/my_instructions.md --out evals/results/mine.json`, then `make regression-eval-vulnerable`. Report each scorer against its threshold, and for every failing row of my run, the message, the tool calls and what the scorer said.

## Done when

`uv run python -m evals.regression --instructions app/data/my_instructions.md` exits 0 and `make regression-eval-vulnerable` reports exit code 1.

## Official docs

- [Datasets](https://docs.orq.ai/ai-studio/optimize/datasets): the rows the eval reads
- [Evaluators](https://docs.orq.ai/ai-studio/optimize/evaluators): LLM-as-a-Judge, like your policy judge
- [Experiments](https://docs.orq.ai/ai-studio/optimize/experiments): where each eval run lands
- [Evaluatorq in orq.ai docs](https://docs.orq.ai/ai-studio/cookbooks/evaluation-safety/evaluator-q): `evaluatorq()`, scorers
- [evaluatorq documentation](https://orq-ai.github.io/evaluatorq/): jobs, datasets, evaluators, and result handling
