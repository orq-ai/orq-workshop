# Evaluate

Part B of the failure analysis module: prove the fix with an eval. Why a fixed set of scored rows beats rereading a few conversations is on the [Evaluate](https://orq-ai.github.io/orq-workshop/evaluate/) stage page; the scorers and thresholds are on the [Concepts](https://orq-ai.github.io/orq-workshop/modules/failure-analysis/concepts/) page.

**Prerequisites:** Part A done, so `app/data/my_instructions.md` exists and `make seed-workspace` has run. **You will have:** a regression eval that passes your fixed instructions and fails the vulnerable ones, with its Experiment runs in the Studio.

## Steps

### Step 1 · The dataset and the judge

`make seed-workspace` created both: the dataset `ws-refund-eval` from [`app/data/dataset.jsonl`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/dataset.jsonl) (20 rows with `inputs.message`, `inputs.expected_decision` and an `expected_output`) and the boolean judge `ws-refund-policy-judge` from [`app/data/judge_prompt.md`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/judge_prompt.md).

Open both in the Studio. The judge's variables are `{{input.user_query}}`, `{{output.response}}` and `{{input.expected_output}}`; it knows only what those tell it. The eval reads the local `dataset.jsonl`, not the Studio copy; add a row when a conversation you analyzed is not covered.

### Step 2 · Run the gate on your fix

```bash
$ uv run python -m evals.regression --instructions app/data/my_instructions.md --out evals/results/mine.json
```

[`evals/regression.py`](https://github.com/orq-ai/orq-workshop/blob/main/evals/regression.py) runs the local agent over every row and compares the mean per scorer with `THRESHOLDS`; exit 0 means every bar was met. `--out` keeps every row's answer, tool calls and explanation; the printed `studio` URL opens the Experiment.

### Step 3 · Run it on the references

```bash
$ make regression-eval              # fixed_instructions.md: should exit 0
$ make regression-eval-vulnerable   # vulnerable_instructions.md: the gate must exit 1
```

A fix near the fixed instructions is good; one that still fails `decision_matches` or `no_pii_leak` sends you back to Part A. LLM judges drift: compare means within one run.

### Step 4 · Read the red cells

Open the Experiment of a failing run and read the failed rows before you change anything. A red row is a prompt problem, a weak expected output, or a judge problem. Never lower a threshold or edit a scorer to make a run pass.

## With your coding agent

Start your coding agent, then paste:

> Read `AGENTS.md` and `modules/failure-analysis/evaluate.md`. Run `uv run python -m evals.regression --instructions app/data/my_instructions.md --out evals/results/mine.json`, then `make regression-eval-vulnerable`. Report each scorer against its threshold, and for every failing row of my run, the message, the tool calls and what the scorer said.

## Done when

`uv run python -m evals.regression --instructions app/data/my_instructions.md` exits 0 and `make regression-eval-vulnerable` reports exit code 1.

## Official docs

- [Experiments](https://docs.orq.ai/ai-studio/optimize/experiments)
- [evaluatorq documentation](https://orq-ai.github.io/evaluatorq/)
