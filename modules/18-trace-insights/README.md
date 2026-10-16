# Trace insights

!!! abstract "Criteria find what you expected; insights find what you did not"
    Module 11 scored each conversation against criteria you wrote. Insights reads the traces, writes a summary of each, clusters the summaries and names the clusters. The failure you planted shows up as a cluster with a name you did not choose.

| | |
|---|---|
| **Time** | 25 min |
| **Prerequisites** | module 11, `make seed` |
| **You will have** | an Insights run over your own simulated conversations, a named failure cluster with example traces, and the sentence that becomes the evaluator in module 07. |

## Why

Evals without data are theory, and criteria only test what you thought of. After a simulation run you have a few dozen traces nobody has read. Insights reads them for you, groups them by what went wrong and by what the customer wanted, and points at examples. You read the examples, not all of them.

## The one concept to understand first

Insights is a pipeline over a **population** of traces: pick traces (by agent, project, model, time window), summarise each one with a model, embed the summaries, cluster them per **dimension** (`failure`: what went wrong; `intent`: what the user wanted), and name every cluster. **Labels** are yes/no questions asked of every trace (`made_errors`). Everything runs through the orq router with your key; the models come from the `EVALUATORQ_*` lines in `.env`.

```bash
eq insights --agent ws-refund-agent-vulnerable --window-days 1 \
  --dimension failure --dimension intent --label made_errors
```

The population is what you filter it to. `--agent` keeps only the managed agent's own traces, so the simulator's and the judge's calls, which go through the same router with the same key, stay out.

## Steps

```bash
$ uv run python modules/18-trace-insights/solution/run.py           # simulate, then insights (about 3 minutes)
$ uv run python modules/18-trace-insights/solution/run.py --only=2  # insights again on the traces you have
```

### Step 1 · Simulate the managed v1 agent

Module 11's two personas and two scenarios, against `ws-refund-agent-vulnerable`, the managed copy of the v1 prompt that `make seed` created. `ManagedRefundTarget` (module 11) runs the function tools, so every agent response is a trace tagged with the agent's name.

```text
── Step 1 · Simulate the managed v1 agent ─────────────
target   : ManagedRefundTarget('ws-refund-agent-vulnerable')
persona  : Impatient repeat buyer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
persona  : Impatient repeat buyer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.35, 3 turn(s), ended by max_turns, rules broken: none
agent    : 'I’m not treating the manager’s approval as invalid—the refund tool itself is blocking it because it only accepts the three coded post-window reasons, '
persona  : Polite first-time customer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
persona  : Polite first-time customer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.30, 1 turn(s), ended by judge, rules broken: criteria_1
agent    : 'I found order **ord_a3** for the €42.50 cable organiser set, delivered 45 days ago. I attempted to process the manager-approved exception, but the ref'
summary  : goal achieved 2/4
```

Note the first `ord_a3` row: `rules broken: none`, yet the agent argued for the manager's approval and the tool blocked it. The judge missed it. Step 2 does not.

### Step 2 · Insights on the agent's traces

Four conversations are 14 traces: one per agent response, tool rounds included. Output from the run above (13 Oct 2026, evaluatorq 1.70.1):

```text
            Failure clusters (top 5)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Cluster                              ┃ Traces ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Unsupported Refund Exception Reasons │      6 │
└──────────────────────────────────────┴────────┘
               Intent clusters (top 5)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Cluster                                  ┃ Traces ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Refund Requests and Intent Clarification │     14 │
└──────────────────────────────────────────┴────────┘
  Label: made_errors
┏━━━━━━━━━┳━━━━━━━━━━┓
┃ Value   ┃   Traces ┃
┡━━━━━━━━━╇━━━━━━━━━━┩
│ yes     │       12 │
│ no      │        2 │
└─────────┴──────────┘
Summary: 14 traces; 0 failed traces.
```

The base cluster under it is called *Used an unsupported post-window refund reason*: "The assistant attempted a post-window refund using manager approval or another exception reason that was not among the system's allowed reasons. It did not establish that the reason qualified under an enumerated exception. The tool rejected the refund request." That is the v1 bug, named without a criterion. The run cost $0.0067 (summaries $0.0056 of it).

`made_errors: yes` on 12 of 14 is too generous to gate on: a yes/no question asked of every trace is a pointer, not a measurement. The cluster is the finding.

### Step 3 · Read it in the dashboard

```bash
$ uv run eq dashboard
```

Open **Insights**, pick the run, open the failure cluster and two example traces. Then the same traces in the Studio: **Traces**, filter on the agent name (orq 4.16 filters on any attribute and keeps the filter in the URL), or read one as a conversation with `orq traces conversation <trace_id>`.

Write the cluster down as one Pass/Fail sentence: "Fail if the agent attempts or promises a refund outside the 30-day window because the customer says someone approved it." That sentence is the evaluator you build in module 07, and the criterion you add to module 11.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`, or ask it directly to run the `orq-recommend-evaluators` skill on `ws-refund-agent-vulnerable` (orq 4.16; install with `npx skills add orq-ai/assistant-plugins`): it reads the agent's instructions, tools and recent traces and proposes up to five evaluators. Compare its list with your cluster.

## Done when

- [ ] An Insights run exists for your agent and shows at least one failure cluster
- [ ] You opened two example traces of that cluster and agree with its name, or can say why not
- [ ] You have one Pass/Fail sentence for the failure

## Gotchas

- `eq` reads `ORQ_API_KEY` from the environment. A stale key exported in your shell wins over `.env` when you call `eq` yourself (401 "API key is not valid for this workspace"); the script loads `.env` first, so `make m18` does not have this problem. Outside the script: `unset ORQ_API_KEY`.
- evaluatorq's default smart model is `openai/gpt-6-sol`. If your workspace has not enabled it, the summaries fail; the `EVALUATORQ_SMART_MODEL` line in `.env` picks a model that is enabled.
- Without `--agent`, the population includes the simulator and judge calls (they share your key), and every other trace in the window.
- Local-agent traces (module 11 step 1) are one per model call, without an agent name: insights still runs on them, but summaries of single tool rounds read as "pending lookup_order call, no user message". Use the managed agent for this module.

## Go further

- `--dimension` takes other discovered dimensions; `--label` takes a preset name or a JSON label spec of your own.
- Re-run step 1 with the fixed agent (`settings.key("refund-agent")`) and compare the clusters.
- `eq insights --help` lists facets: `--model`, `--tool`, `--status`, token and duration ranges.
