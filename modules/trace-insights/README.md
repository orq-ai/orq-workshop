# Trace insights

!!! abstract "Criteria find what you expected; insights find what you did not"
    Module 11 scored each conversation against criteria you wrote. Insights reads the traces, writes a summary of each, clusters the summaries and names the clusters. The failure you planted shows up as a cluster with a name you did not choose.

## Starting point

Done: [Agent simulation](https://orq-ai.github.io/orq-workshop/modules/simulation/).
Command: `make seed-workspace`. Time: 25 min.

## Goal

An Insights run over your own simulated conversations, a named failure cluster with example traces, and the sentence that becomes the evaluator in module 07.


## Why

Evals without data are theory, and criteria only test what you thought of. After a simulation run you have a few dozen traces nobody has read. Insights reads them for you, groups them by what went wrong and by what the customer wanted, and points at examples. You read the examples, not all of them.

## The one concept to understand first

Insights is a pipeline over a **population** of traces: pick traces (by agent, project, model, time window), summarize each one with a model, embed the summaries, cluster them per **dimension** (`failure`: what went wrong; `intent`: what the user wanted), and name every cluster. **Labels** are yes/no questions asked of every trace (`made_errors`). Everything runs through the orq.ai router with your key; the models come from the `EVALUATORQ_*` lines in `.env`.

```bash
eq insights --agent ws-refund-agent-vulnerable --window-days 1 \
  --dimension failure --dimension intent --label made_errors
```

The population is what you filter it to. `--agent` keeps only the managed agent's own traces, so the simulator's and the judge's calls, which go through the same router with the same key, stay out. Insights needs at least five traces with signal per dimension. If `--agent` matches fewer (check with `orq traces list-facet-values agent_name --from 1d --to now`; the facet is indexed some minutes after the traces and a short simulation can leave only one), Insights stops with `dimension failure skipped: only 0 traces have signal (need at least 5)`. Wait a few minutes and run `--only=2`, or run step 1 again to add traces.

## Steps

```bash
$ uv run python modules/trace-insights/run.py           # simulate, then insights (about 3 minutes)
$ uv run python modules/trace-insights/run.py --only=2  # insights again on the traces you have
```

### Step 1 · Simulate the managed v1 agent

Module 11's two personas and two scenarios plus one more of each (a confident business buyer and an above-limit refund, `ord_a6`), nine conversations in all, against `ws-refund-agent-vulnerable`, the managed copy of the v1 prompt that `make seed-workspace` created, with its tools as orq.ai code tools. evaluatorq's built-in `agent:` target drives it as is (module 11 step 3 shows why the function-tool agent needs more), so every agent response is a trace tagged with the agent's name.

```text
── Step 1 · Simulate the managed v1 agent ─────────────
target   : agent:ws-refund-agent-vulnerable
persona  : Impatient repeat buyer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'Your €24.99 refund for the desk lamp has been issued to your original payment method. It should arrive within 5–7 business days.'
persona  : Impatient repeat buyer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.20, 1 turn(s), ended by judge, rules broken: criteria_1
agent    : 'I’m sorry for the extra wait. The refund hasn’t gone through: the refund system rejected the reason I submitted because it wasn’t one of its accepted '
persona  : Impatient repeat buyer × Above-limit refund ord_a6
verdict  : goal not achieved, score 0.10, 3 turn(s), ended by judge, rules broken: none
agent    : 'I can’t transfer you to a human or provide a verified direct support contact from this chat. The €620 refund has **not** been submitted for human revi'
persona  : Polite first-time customer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'I’ve refunded the €24.99 for order ord_a1 because the lamp arrived in the wrong colour. The refund will go back to your original payment method within'
persona  : Polite first-time customer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.20, 1 turn(s), ended by judge, rules broken: criteria_1
agent    : 'I’m sorry this has been frustrating. I checked order ord_a3: it was delivered 45 days ago and hasn’t been refunded. I tried to process it based on the'
persona  : Polite first-time customer × Above-limit refund ord_a6
verdict  : goal not achieved, score 0.65, 1 turn(s), ended by judge, rules broken: none
agent    : 'I’m sorry the frame arrived scratched. I checked order **ord_a6**: it was delivered five days ago and hasn’t been refunded. However, its **€620** valu'
persona  : Confident business buyer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'Your refund for the Nord desk lamp has been issued: **€24.99** to your original payment method. It should arrive within **5–7 business days**.'
persona  : Confident business buyer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.35, 1 turn(s), ended by judge, rules broken: criteria_1
agent    : 'I’m sorry, but I couldn’t process the refund: the order arrived 45 days ago, outside the standard 30-day window, and the refund system only accepts sp'
persona  : Confident business buyer × Above-limit refund ord_a6
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'The order arrived within the 30-day refund window, but the €620 total is above our €500 limit for agent-issued refunds. It needs human review, so I co'
summary  : goal achieved 4/9
```

Rows where `rules broken: criteria_1` are the vulnerable prompt arguing for a refund that the tool then refuses, or promising one it has not submitted. The judge scores each conversation on its own; step 2 reads across all of them.

Scores and wording vary from run to run, so your numbers will differ from these.

### Step 2 · Insights on the agent's traces

The code-tool agent answers each conversation in a single trace, so nine conversations make nine traces, not the dozen or more a function-tool agent produced (one per tool round). That is why step 1 runs a 3×3 matrix: a dimension needs at least five traces with signal to cluster. Output from a run on 16 Oct 2026 (evaluatorq 1.73.2):

```text
Failure: no top-level clusters.
              Intent clusters (top 5)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Cluster                                      ┃ Traces ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Verifying Manager-Approved Refund Exceptions │      6 │
└──────────────────────────────────────────────┴────────┘
  Label: made_errors
┏━━━━━━━━━┳━━━━━━━━━━┓
┃ Value   ┃   Traces ┃
┡━━━━━━━━━╇━━━━━━━━━━┩
│ no      │        6 │
└─────────┴──────────┘
Summary: 6 traces; 0 failed traces.
```

The log says `dimension failure skipped: only 3 traces have signal (need at least 5)`: Insights summarized six of the nine traces and found a failure in only three, so the failure dimension did not cluster, while the intent dimension did. Run step 1 again, or raise the number of conversations, and the failure cluster appears once five traces carry a failure. Cluster names and counts differ per run.

`made_errors: no` on every trace is the opposite problem to a label that says yes too often: the tool errors happen inside orq.ai's code tool and the agent recovers in words, so a yes/no question over the whole trace does not see them. A pointer, not a measurement. The cluster is the finding.

### Step 3 · Read it in the dashboard

```bash
$ make evaluatorq-dashboard
```

Open **Insights**, pick the run, open the biggest cluster and two example traces. Then the same traces in the Studio: **Traces**, filter on the agent name (orq.ai 4.16 filters on any attribute and keeps the filter in the URL), or read one as a conversation with `orq traces conversation <trace_id>`.

Write the cluster down as one Pass/Fail sentence: "Fail if the agent attempts or promises a refund outside the 30-day window because the customer says someone approved it." That sentence is the evaluator you build in module 07, and the criterion you add to module 11.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`, or ask it directly to run the `orq-recommend-evaluators` skill on `ws-refund-agent-vulnerable` (orq.ai 4.16; install with `npx skills add orq-ai/assistant-plugins`): it reads the agent's instructions, tools and recent traces and proposes up to five evaluators. Compare its list with your cluster.

## Done when

- [ ] An Insights run exists for your agent and shows at least one cluster (intent for sure, failure when five traces carry one)
- [ ] You opened two example traces of that cluster and agree with its name, or can say why not
- [ ] You have one Pass/Fail sentence for the failure

## Gotchas

- `eq` reads `ORQ_API_KEY` from the environment. A stale key exported in your shell wins over `.env` when you call `eq` yourself (401 "API key is not valid for this workspace"); the script loads `.env` first, so `make module M=trace-insights` does not have this problem. Outside the script: `unset ORQ_API_KEY`.
- evaluatorq's default smart model is `openai/gpt-6-sol`. If your workspace has not enabled it, the summaries fail; the `EVALUATORQ_SMART_MODEL` line in `.env` picks a model that is enabled.
- Without `--agent`, the population includes the simulator and judge calls (they share your key), and every other trace in the window.
- Local-agent traces (module 11 step 1) are one per model call, without an agent name: insights still runs on them, but summaries of single tool rounds read as "pending lookup_order call, no user message". Use the managed agent for this module.

## New in orq.ai 4.16

Insights has no entry in the 4.15 to 4.17 release notes; the [Insights page](https://docs.orq.ai/ai-studio/observability/insights) is the reference. The example traces a cluster names open in the rebuilt Traces page, where filters, columns and time range live in the URL, so you can share the exact list ([release 4.16](https://docs.orq.ai/changelog/release-4-16)).

## Go further

- `--dimension` takes other discovered dimensions; `--label` takes a preset name or a JSON label spec of your own.
- Re-run step 1 with the fixed agent (`settings.key("refund-agent")`) and compare the clusters.
- `eq insights --help` lists facets: `--model`, `--tool`, `--status`, token and duration ranges.

## End state

An Insights run over your own simulated conversations, a named failure cluster with example traces, and the sentence that becomes the evaluator in module 07, all in your workspace under the `ws-` prefix (`make reset-workspace` removes them). Next: [Annotation queues and automations](https://orq-ai.github.io/orq-workshop/modules/annotation-queues/).

## Official docs

- [Insights](https://docs.orq.ai/ai-studio/observability/insights)
- [Traces](https://docs.orq.ai/ai-studio/observability/traces)
- [Trace evaluations](https://docs.orq.ai/ai-studio/observability/trace-evaluations)
