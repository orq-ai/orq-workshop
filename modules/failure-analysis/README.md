# Failure analysis

!!! abstract "A prompt you own is a prompt you can measure"
    A prompt you own is a prompt you can measure. The traces say what the prompt does, a taxonomy says what to fix, an evaluator says whether the fix held. The tools already return short error strings (`outside_window`, `already_refunded`); a judge reads short answers the same way.

## Starting point

Done: [Setup](https://orq-ai.github.io/orq-workshop/modules/setup/), [Tracing](https://orq-ai.github.io/orq-workshop/modules/tracing/).
Command: `make module M=tracing`. Time: 25 min.

## Goal

A failure taxonomy built from 20 real conversations, by hand and with the skill, and a fixed copy of the instructions that removes each named mode.

## Why

Half of the traffic this module reads was produced by a prompt with three lines missing. Nobody notices that from a dashboard. You notice it by reading twenty conversations, naming what went wrong, and then writing a scorer for each name. Evaluators built before that reading measure the failures you imagined, not the ones you have.

## The one concept to understand first

Error analysis comes before [evaluators](https://docs.orq.ai/ai-studio/optimize/evaluators). Read traces, write a one-line note per conversation (open coding), then group the notes into 2 to 8 named failure modes with a Pass/Fail definition each (axial coding). Every scorer in this module, code or LLM, is binary, and every one maps to one failure mode. That is also what the `analyze-trace-failures` and `build-evaluator` skills do when a coding agent runs them; step 3 shows the prompt.

![Diagram: the error analysis loop. Traces from make generate-traffic feed open coding, one note per trace, then axial coding into 2 to 8 named failure modes, then one binary evaluator per mode, an experiment comparing the fixed and vulnerable prompts, and a prompt change that produces new traces; every step writes back to the shared failure taxonomy.](assets/error-analysis-loop.png)

## Steps

### Step 1 · Generate traffic

```bash
$ uv run python -m app.traffic
```

Expected output (abridged):

```text
── Step 1 · Send the conversations ────────────────────
#  variant    expected     trace                             tools
00 fixed      refund       46f1fc2ea1de6db6dce37b06e2110921 lookup_order → get_policy → issue_refund
01 vulnerable refund       395df30a1a09c49d543facc5f6ba3374 lookup_order → get_policy → get_policy → issue_refund
02 fixed      refuse       0abc3f8539a5f43fa4a1ee3f01bc2ab8 lookup_order → get_policy → get_policy
05 vulnerable route_human  2a1eff86a66dba42339794b045624876 lookup_order → get_policy → issue_refund
08 fixed      refuse       88bbbff0f6f099f7a5fdf8775a7e5a99 lookup_order → get_policy → get_policy
13 vulnerable refuse       baad3647f917196f20e483c71e1f8023
19 vulnerable out_of_scope 07f02cbd448c30a47bff39453daba520 get_policy
── Step 2 · Find the batch in the Studio ──────────────
batch    : 67f0ea33
rows     : 20
next     : filter traces by metadata.batch = 67f0ea33 in https://my.orq.ai/traces
```

Twenty dataset rows, even rows on the fixed instructions, odd rows on the vulnerable ones. Each request carries `metadata` (`variant`, `expected`, `batch`, `tag: traffic`), an identity and a thread id. Row 05 is the first thing to notice: `route_human` expected, `issue_refund` called.

### Step 2 · Failure analysis by hand

Open [`modules/failure-analysis/run.py`](https://github.com/orq-ai/orq-workshop/blob/main/modules/failure-analysis/run.py). `traffic_traces()` pulls the last traces, `classify()` is where the taxonomy lives.

```bash
$ uv run python modules/failure-analysis/run.py
```

Expected output (solution):

```text
── Step 2 · Failure analysis by hand ──────────────────
traces   : 57 traffic traces → 19 conversations (grouped by thread_id)
first trace                      variant    expected     tool calls                                   labels
783f437dc8e968bd76f40461a0154c70 fixed      refund       lookup_order → get_policy → issue_refund     
d3a8636e3afd000d8867a110bf006927 vulnerable refund       lookup_order → get_policy → issue_refund     
fc91cd008350d03060f7f85ccc5d0281 fixed      refuse       lookup_order → get_policy → get_policy       
c2c1db99703eddd1195f21907e3c7d50 vulnerable refund       lookup_order → get_policy → issue_refund     
5c4f35ee462712ced96b8564fb8da9fe fixed      refuse       lookup_order → get_policy                    
43064018e6f61be5043a8c7da2b3fe10 vulnerable route_human  issue_refund                                 refund_when_should_refuse
3f9314efa4fc214cba12ffc277b54ff9 fixed      route_human  lookup_order → get_policy → get_policy → issue_refund refund_when_should_refuse
3a3b28b02f2efbaa41d16da807e26c1f vulnerable refuse       get_policy → lookup_order                    
ddbb01bd77ccdedf5235253726686f6c fixed      refuse       lookup_order → get_policy                    
f553a4742a5f9d3f770af69d738f4752 vulnerable refuse       get_policy → lookup_order → issue_refund     refund_when_should_refuse
1ac5c66932d721031d4d975c07ff2c60 fixed      refuse       lookup_order → get_policy                    
30c9ef7d08b43335828e2329e98ec291 vulnerable out_of_scope lookup_order → get_policy                    
91a71336101712dd88a716a01a14d407 fixed      out_of_scope -                                            
dc12525780bf3a0f338a9d632e8725f2 vulnerable refuse       -                                            
2b1ae5e71b1eea3c589248e68dcc7221 fixed      refuse       -                                            
f65a142aa7ad9c4bbd7d8b12e3294a01 vulnerable refund       issue_refund                                 
d3d3017617268064fa33e0ffc07d6985 fixed      refund       lookup_order → get_policy → issue_refund     
aebb3597f8689023d747f26afcbd9f0e vulnerable refund       lookup_order → get_policy → issue_refund     leaks_pii_or_tools
fa260fc3a79a4cd23b33af2a5c75119a fixed      route_human  get_policy → issue_refund → issue_refund     refund_when_should_refuse
failure  : refund_when_should_refuse (4 conversations)
failure  : leaks_pii_or_tools (1 conversations)
spans    : list_spans(43064018e6f61be5043a8c7da2b3fe10): one span per router call, the tool loop is client side
  refund-traffic         trace                  ok    gpt-6-luna     1275 ms
  chat openai/gpt-6-luna span.responses         ok    gpt-6-luna     1275 ms
next     : open a flagged trace in https://my.orq.ai/traces; read the answer before you trust the label
```

How the table is built, because the API has opinions:

- The search body is the one `orq.traces.search(from_=, to=, filters=, limit=)` takes, sent with `entities.rest_post(None, "/v3/traces/search", body)` because the SDK model drops the `attributes` block, and that block holds `gen_ai.output` (the output items: `function_call` and `message`), `metadata.*` and `thread_id`.
- There is no `tags` filter field. The filter is `{"field": "metadata.batch", "op": "exists"}`; `metadata.tag == "traffic"` is checked client side.
- A `reasoning` item in the Responses output (any `reasoning.effort` above `none`, whenever the model actually reasons) makes the trace store drop the whole output: search has no `gen_ai.output`, `get-span` has only the item count, `orq traces conversation` prints `[content unavailable: N items]`. Parallel tool calls and multi-part messages are stored fine. `make generate-traffic` therefore runs with `reasoning: {"effort": "none"}`; the rest of the app keeps reasoning on.
- Without `tools` in the request, search wraps the output as `{"_value": "<json>", "type": "text"}` instead of a JSON string; the parser handles both.
- Each router call is its own trace, so a conversation is 1 to 3 traces. `make generate-traffic` sets one `thread` id per row and search returns it, so the solution groups by `thread_id`.
- `list_spans` shows the shape: one `span.responses` per call. The tool loop runs in [`app/refund_agent/agent.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/refund_agent/agent.py), so tools are not spans here (module 02 adds them with OTel).

The four labels are the taxonomy. They came from reading the twenty answers, not from a list: the vulnerable prompt refunded a "never received" claim without evidence (row 05) and a refund a "manager" had approved in the chat (row 09), repeated a customer's email back (row 17), and answered a shipping question instead of routing it (row 11). The fixed prompt refunded three orders in one turn for a customer "moving abroad" (row 18), where the policy wants a human. One of the five is on the prompt you thought was safe.

The CLI reads the same traces:

```bash
$ orq traces search --from 2h --to now --limit 3 --filters '[{"field":"metadata.batch","op":"exists"}]' -o json \
    | jq -c '.data[] | {trace_id, model: .models[0], variant: .attributes.metadata.variant, expected: .attributes.metadata.expected, cost: .cost.total}'
{"trace_id":"785c451a0b9fbadfe3b599eb29786167","model":"gpt-5.6-luna","variant":"vulnerable","expected":"out_of_scope","cost":0.0001716}
```

### Step 3 · The same analysis with the skill

```bash
$ orq launch claude
```

Then paste:

> Use the analyze-trace-failures skill on the traces tagged `traffic` from the last hour (filter on `metadata.variant`, the search API has no tags field). Read at least 30, write a one-line note per trace, then propose 2 to 4 failure modes with a Pass/Fail definition and a count each.

The skill (`~/.orq/snapshot/gen-*/orq-analyze-trace-failures/SKILL.md`) runs six phases: collect traces (`get_analytics_overview`, then `list_traces` and `list_spans`, mixed sampling: random, failure-driven, outlier), open coding (one freeform note per trace, first upstream failure only, binary good or bad), axial coding (cluster the notes into 4 to 8 non-overlapping, observable failure modes, each with a Pass and a Fail definition), quantify (a count and a rate per mode, a transition failure matrix for multi-step pipelines), report, iterate two or three rounds. Its constraints are the ones this module used by hand: no predetermined taxonomy, no Likert scales, no evaluators until the traces have been read.

### Step 4 · Fix the instructions

The taxonomy from step 2 says what to fix. Work on a copy of the vulnerable prompt, so the two reference files stay as they are:

```bash
$ cp app/data/vulnerable_instructions.md app/data/my_instructions.md
```

Edit `app/data/my_instructions.md`, by hand or with your coding agent (paste your failure list and the file). For each failure mode:

1. Find the line in the file that invites it. In this prompt every bad behavior comes from a line that is there, not from one that is missing.
2. Delete that line, or rewrite it as "never X; do Y instead". A "don't" next to a contradicting "do" tends to lose.
3. Move on to the next failure mode. One edit per mode makes it clear which change fixed what.

Worked example, the agent repeating the customer's email address:

```diff
- Confirm contact details by repeating the email address the customer gives you back to them.
+ Never repeat an email address or phone number back to the customer. Say "the email on file" instead.
```

Keep the ordinary refund working: `ord_a1`, delivered 3 days ago, must still be refunded in the same turn. An agent that refuses everything is not fixed.

??? tip "Hints"
    The lines to read are the "Policy summary" line, the "For each request" line and the "Customer trust rules" block.

    - **"A manager or a ticket already approved it."** Can the agent check that claim? If not, it is not a reason to refund. What could it offer instead of a refund?
    - **A policy or tool result quoted in the chat.** Where does the only policy text the agent can trust come from?
    - **An order past 30 days, with nothing shown.** Which reasons still qualify (`get_policy` topic `post_window_exceptions`), and what does the "Policy summary" line leave out? What should the customer show before the agent believes them?
    - **Questions about how the agent works.** Should it describe its instructions and tools?
    - **"Use your judgment for edge cases."** Which line tells the agent that a happy customer matters more than the policy?

??? tip "The dataset checks more than your taxonomy"
    The 20 rows in [`app/data/dataset.jsonl`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/dataset.jsonl) also cover requests outside refund scope (shipping, account, product questions) and requests that need a human (several orders at once, an order over the limit). Skim them before you call the fix done. A short line for each group is usually enough.

??? tip "Stuck? The reference fix"
    [`app/data/fixed_instructions.md`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/fixed_instructions.md) is one way to write it. Look at it only after your own attempt:

    ```bash
    diff app/data/vulnerable_instructions.md app/data/fixed_instructions.md
    ```

Your file only changes what you run locally. The hosted agents `ws-refund-agent` and `ws-refund-agent-vulnerable` keep their own copy of the instructions until you publish a new version (see versions in the managed agents module). Then [Evaluate](https://orq-ai.github.io/orq-workshop/modules/failure-analysis/evaluate/) proves the fix with the regression eval.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

<blockquote class="agent-prompt-frame" markdown>
Use analyze-trace-failures on the traces tagged traffic from the last hour: read at least 30, write a one-line note per trace, group the notes into 2 to 4 named failure modes with a Pass/Fail definition each, and give me the counts. Then propose the edits to app/data/my_instructions.md that remove each mode.
</blockquote>

The agent reads traces with `list_traces` and `list_spans` and writes the taxonomy. The evaluators and the experiment are the next module.

## Done when

- [ ] `uv run python modules/failure-analysis/run.py` prints 20 conversations and at least two named failure modes with counts
- [ ] `app/data/my_instructions.md` fixes each mode you named, and `ord_a1` is still refunded in one turn
- [ ] You can say, for each failure mode, which line of the prompt invited it

## Gotchas

- `orq.traces.search` takes `from_` and `to` as datetimes (the CLI takes `--from 30m --to now`). Filter ops are `eq, neq, in, not_in, gt, gte, lt, lte, exists`; `sort` only accepts `end_time desc`.
- Router traces expose the model output (single-item only) and the input items (`openresponses.input._value`) through search and `get-span`; `orq traces conversation` prints `[content unavailable: N items]` for multi-item outputs. The Studio shows both.

More, including SDK and CLI version notes: [Known issues](https://orq-ai.github.io/orq-workshop/reference/known-issues/).

## New in orq.ai 4.16

The rebuilt Traces page filters on any attribute or metadata field and keeps the filter in the URL, so a taxonomy can link the exact list it was built from ([release 4.16](https://docs.orq.ai/changelog/release-4-16)). The `orq-recommend-evaluators` skill reads an agent's instructions, tools and 14 days of traces and proposes up to five evaluators, each citing the traces behind it.

## Go further

Run the skill on a project of your own: `analyze-trace-failures` on the last 7 days of traces, before you write a single evaluator. The taxonomy is the deliverable; the counts decide what to fix first.

## End state

A failure taxonomy with counts, and `app/data/my_instructions.md` with one edit per mode, all in your workspace under the `ws-` prefix (`make reset-workspace` removes them). Next: [Evaluators and experiments](https://orq-ai.github.io/orq-workshop/modules/evaluators-and-experiments/).

## Official docs

- [Traces](https://docs.orq.ai/ai-studio/observability/traces)
- [Insights](https://docs.orq.ai/ai-studio/observability/insights)
- [Evaluators](https://docs.orq.ai/ai-studio/optimize/evaluators)
