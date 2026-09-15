# 15 · Advisor and sidekick

!!! abstract "Factor 10: Small, focused agents, Factor 3: Own your context window"
    One agent on one model runs every step. The `advisor` and `sidekick` tools hand single steps to a second model configured at design time, each metered on its own span. Neither is a sub-agent: one call, no tools, no memory of its own.

| | |
|---|---|
| **Time** | 30 min |
| **Prerequisites** | module 08, `make seed` |
| **You will have** | a refund agent that consults `gpt-5.6-sol` only before a refusal and delegates the closing note to `gpt-5.4-nano`, with the cost of each choice read off one trace. |

## Why

Size the agent's model for the hardest step and every routine step pays for it. Size it for the routine steps and it fails exactly where quality matters. The refund agent has both kinds of step: reading an order and a policy is mechanical; deciding whether a refusal is consistent with the policy is a judgement; writing the closing note is formatting. Delegation lets each step run on the model it deserves, and the trace shows what that cost.

## The one concept to understand first

Two tools, two contracts. Ask whether the step needs the conversation history.

| | Advisor | Sidekick |
|---|---|---|
| Sends | the transcript, plus a question | a task, and nothing else |
| Returns | advice | a finished artifact |
| Who decides | the agent | the sidekick |
| Use when | a judgement that depends on what came before | self-contained work the conversation does not need |
| Extra config | `max_transcript_tokens` | `system_prompt`, `output_format` |

Both are entries in `settings.tools` with the secondary model in `configuration`:

```python
{"type": "advisor",  "configuration": {"model": "openai/gpt-5.6-sol", "max_uses": 2, "max_transcript_tokens": 4000, "max_tokens": 400}},
{"type": "sidekick", "configuration": {"model": "openai/gpt-5.4-nano", "max_uses": 2, "max_tokens": 200,
                                       "system_prompt": "Write short, warm customer-service closing notes ...", "output_format": "Two sentences."}},
```

![Diagram: one turn of the delegating agent. The agent on gpt-5.6-luna runs lookup_order and get_policy, calls the advisor (transcript plus a question goes to gpt-5.6-sol, advice comes back), decides, calls the sidekick (task only goes to gpt-5.4-nano, a closing note comes back), and answers. Each secondary call is its own nested span with its own cost.](assets/delegation-turn.png)

The instructions matter more than the configuration. A tool the instructions never mention is rarely called: name each tool at the step it belongs to, and say that the routine work stays on the agent's own model.

## Steps

Open `modules/15-advisor-sidekick/run.py`. Steps 3, 4 and 5 are `TODO`s. The solution is in `solution/run.py`.

### Step 1 · Inspect the delegating agent

```bash
$ orq agents retrieve ws-refund-agent-delegating -o json | jq '.settings.tools[] | select(.action_type == "advisor" or .action_type == "sidekick") | {action_type, configuration}'
$ uv run python modules/15-advisor-sidekick/run.py
```

Expected output:

```text
── Step 1 · Inspect the delegating agent ──────────────
agent    : ws-refund-agent-delegating v1.0.6 model=openai/gpt-5.6-luna
base     : ws-refund-agent model=openai/gpt-5.6-luna
advisor  : model=openai/gpt-5.6-sol max_uses=2 max_transcript_tokens=4000
sidekick : model=openai/gpt-5.4-nano max_uses=2 output_format='Two sentences.'
rules    : - Before refusing a post-window or above-limit request, ask the advisor whether ... / - After any refund decision, delegate writing the two-sentence customer-facing c...
next     : Agents > ws-refund-agent-delegating > Tools in the Studio: the two delegation tools next to the three function tools
```

The version is `v1.0.0` on a fresh seed; module 14 bumps it every time it touches the description.

`make seed` built it from the fixed refund agent (`app/refund_agent/entities.py`, `ensure_delegating_agent`). Open it in the Studio (**Agents** > `ws-refund-agent-delegating` > **Tools**): the two delegation tools sit next to the three function tools, each with its model.

### Step 2 · Run a refund the agent has to refuse

`ord_a6` is a EUR 620 frame; the policy caps refunds at EUR 500. The instructions send the agent to the advisor before it refuses and to the sidekick for the closing note. The loop is module 08's: execute the `function_call` items that are yours, skip the ones with an `orq:*` sibling, continue with `previous_response_id`.

```text
── Step 2 · Run a refund the agent has to refuse ──────
question : Refund ord_a6 please, the frame arrived scratched.
tools    : lookup_order → get_policy
delegate : advisor, sidekick
steps    : 3 responses in 14.8s
answer   : Hi! Thanks for sharing—because your order amount is EUR 620, which is above our EUR 500 threshold, i…
trace    : 42c275433f70ab0f3cd46a2a6908a0a0
next     : orq traces thread 42c275433f70ab0f3cd46a2a6908a0a0
```

No `issue_refund` in the list: luna reads the EUR 620 off `lookup_order`, knows the limit from `get_policy`, and goes to the advisor before ever trying the tool. On gpt-4o-mini the same agent tried the refund first and let the tool's limit error send it to the advisor; a stronger base model moves the judgement earlier.

### Step 3 · Read what each tool sent and got back

Both tools show up twice in the output items: a `function_call` with the arguments the agent wrote, then an `orq:advisor` or `orq:sidekick` item with the result. The advisor's arguments are a question, and the platform adds the transcript; the sidekick's are the task and nothing else.

```text
── Step 3 · Read what each tool sent and got back ─────
tool     : orq:advisor
sent     : 'Confirm whether refusing this refund and routing it to human review is consistent with the fetched p'
got      : '1. Yes—routing the request to human review is consistent because EUR 620 exceeds the EUR 500 single-'
tool     : orq:sidekick
sent     : 'Write a concise, customer-facing closing note in exactly two sentences. Mention the order amount thr'
got      : 'Hi! Thanks for sharing—because your order amount is EUR 620, which is above our EUR 500 threshold, i'
next     : the advisor got the transcript too; the sidekick got only the task line above
```

Read the advice again: the agent asked whether refusing and routing to human review is consistent with the policy, the advisor confirmed it point by point, and the sidekick wrote the closing note the agent then returned verbatim. The judgement went to the stronger model, the decision stayed with the agent.

### Step 4 · Read the cost split in the trace

Each secondary call goes through the AI Gateway on its own, so it appears as a nested span with its own cost: `advisor` (`span.tool`) > `chat gpt-5.6-sol`, `sidekick` > `chat gpt-5.4-nano`. Sum the agent's own `chat openai/gpt-5.6-luna` spans and compare.

```text
── Step 4 · Read the cost split in the trace ──────────
total    : $0.00530 over 3 traces
    agent     gpt-5.6-luna   calls=5  $0.00092   17.3%
    advisor   gpt-5.6-sol    calls=1  $0.00428   80.7%
    sidekick  gpt-5.4-nano   calls=1  $0.00011    2.0%
next     : orq traces get-span 42c275433f70ab0f3cd46a2a6908a0a0 <span_id> for any row above, or open the trace in the Studio
```

One advisor call cost more than four times the agent's five calls together, four fifths of the turn. That is the number to argue about: is a correct escalation decision worth quintupling the turn? Here, yes. For a question like "what is the refund window", no, and the instructions make sure the advisor is not asked.

```bash
$ orq traces thread 42c275433f70ab0f3cd46a2a6908a0a0
```

Open the trace in the Studio: the `advisor` and `sidekick` spans sit under `agent.response`, with the `chat gpt-5.6-sol` and `chat gpt-5.4-nano` spans under them, each with its own cost.

### Step 5 · When the secondary model fails

A copy of the agent points its advisor at a model that does not exist. The turn does not fail: the `orq:advisor` item carries the error text, the advisor span stays `ok` with no chat span underneath, and the agent answers from its own model.

```text
── Step 5 · When the secondary model fails ────────────
created  : ws-refund-agent-delegating-broken
agent    : ws-refund-agent-delegating-broken (advisor on openai/gpt-does-not-exist)
tools    : lookup_order → get_policy
answered : yes
advisor  : "advisor: secondary model request failed: Model 'openai/gpt-does-not-exist' not found or is not avail"
trace    : 61a6083e9f1989c97acdedccbdf52907: 1 advisor span(s), status=ok cost=$0.00000, no chat span underneath
verdict  : the turn did not fail; the failure is in the orq:advisor item, not in the HTTP status
next     : watch for it in the trace, not in genai.error_rate
```

So a broken advisor degrades quality silently: the agent read "secondary model request failed" as advice and carried on. Watch for it in the trace, not in the HTTP status.

### Step 6 · The same from the CLI

```bash
$ orq responses create --model agent/ws-refund-agent-delegating --input '"Refund ord_a6 please, the frame arrived scratched."' -o json | jq '[.output[] | select(.type | startswith("orq:")) | {type, result}]'
```

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the build-agent skill to create an agent `ws-refund-agent-triage`, a copy of `ws-refund-agent-delegating` with the `advisor` on `anthropic/claude-sonnet-5` and `max_uses` 1. Invoke both agents with "Refund ord_a6 please, the frame arrived scratched.", execute the `function_call` items with `app.refund_agent.tools.dispatch`, and give me a two-row table from the traces: advisor model, advisor span cost, agent's own cost, total, and whether the advice changed the decision.

## Done when

- [ ] A run of `ws-refund-agent-delegating` on `ord_a6` shows `delegated=['advisor', 'sidekick']`
- [ ] You can point at the advisor's question and the sidekick's task in the output items, and say which one carried the transcript
- [ ] The cost split names the most expensive span of the turn and you can defend it
- [ ] `ws-refund-agent-delegating-broken` still answers, and you found the failure in the `orq:advisor` item

## Gotchas

- The delegation tools are `advisor` and `sidekick` on Agents. On the gateway's server tools they are `orq:advisor` and `orq:subagent`; `orq:sidekick` is a legacy alias.
- Nested tool spans arrive a few seconds after the response. `list_spans` straight after the call can miss the sidekick; the solution sleeps five seconds.
- The root span of type `trace` repeats the agent's own model cost. Skip it when summing, or the agent's share doubles.
- `max_uses` is per turn. With `max_uses: 2` the agent may ask the advisor twice; the broken agent did.
- A secondary model that fails does not fail the turn and does not error the span. Alerting on `genai.error_rate` will not see it (module 14); reading the `orq:advisor` result will.

## New in orq 4.13

Advisor and Sidekick tools on Agents, metered separately with their own spans. 4.12 added a configurable timeout per agent tool, which applies to these too.

## Go further

- Give the sidekick a structured `output_format` (a JSON schema in prose) and parse the artifact in your loop instead of returning it verbatim.
- Swap the advisor to a reasoning model and compare the cost split; the transcript cap (`max_transcript_tokens`) is what keeps that affordable.
- Docs: [Advisor and Sidekick cookbook](https://docs.orq.ai/docs/ai-studio/cookbooks/common-architecture/advisor-and-sidekick), [Build agents](https://docs.orq.ai/docs/ai-studio/ai-engineering/build-agents), [Traces](https://docs.orq.ai/docs/ai-studio/observability/traces).
