# 12-Factor Agents map

[12-Factor Agents](https://github.com/humanlayer/12-factor-agents) by HumanLayer is a set of principles for building LLM software that ships. It is a reading aid here, not the syllabus: each module's opening box names the factor it exercises and the one orq surface that embodies it, and this page is the index of those boxes. The sample app is written that way on purpose.

| Factor | Modules | Where it shows in orq |
|---|---|---|
| 1 · Natural language to tool calls | [01](modules/01.md), [08](modules/08.md) | function calling through the router; `function_call` output items from a managed agent |
| 2 · Own your prompts | [07](modules/07.md), [08](modules/08.md) | instructions as repo files, agent versions, the `optimize-prompt` skill, experiments that compare prompts |
| 3 · Own your context window | [02](modules/02.md), [09](modules/09.md), [15](modules/15.md) | traces show the exact context sent; knowledge base `top_k`, threshold and rerank decide what enters; the advisor gets the transcript, the sidekick only the task |
| 4 · Tools are just structured outputs | [08](modules/08.md), [10](modules/10.md) | the app executes `function_call` items itself; the MCP Gateway exposes a chosen subset of tools |
| 5 · Unify execution state and business state | [02](modules/02.md), [08](modules/08.md) | identity and thread on every call; memory `entity_id`; the order store |
| 6 · Launch, pause, resume with simple APIs | [08](modules/08.md), [12](modules/12.md) | `previous_response_id`, `responses.retrieve`, streaming; headless `orq launch -p` |
| 7 · Contact humans with tool calls | [04](modules/04.md), [08](modules/08.md), [17](modules/17.md) | a blocked guardrail as the escalation path; `tool_approval_required`; an `escalate_to_human` tool; an annotation queue a human reviews and an automation that fills it |
| 8 · Own your control flow | [01](modules/01.md), [04](modules/04.md), [08](modules/08.md) | the loop in `agent.py`; routing rules; guardrail rules; `max_iterations` |
| 9 · Compact errors into the context window | [01](modules/01.md), [07](modules/07.md) | short tool error strings; fallbacks and retry; a failure taxonomy |
| 10 · Small, focused agents | [10](modules/10.md), [15](modules/15.md), [16](modules/16.md) | a gateway that exposes a subset; red teaming shows what a big surface costs; advisor and sidekick hand one step to a second model |
| 11 · Trigger from anywhere | [02](modules/02.md), [10](modules/10.md), [12](modules/12.md), [13](modules/13.md), [14](modules/14.md) | any framework through the gateway; MCP consumers; CI cron; coding agents; alerts, webhooks and trace automations trigger work without a human |
| 12 · Make your agent a stateless reducer | app, [07](modules/07.md), [11](modules/11.md) | `run_turn(messages) -> messages`; evaluatorq `@job`; simulation replay |
| 13 · Pre-fetch all the context you might need | [09](modules/09.md) | gateway-side `knowledge_bases` on a plain chat call; `lookup_order` before the model speaks |

## The app, factor by factor

```python
# app/refund_agent/agent.py
def run_turn(messages, *, store=None, extra_body=None, ...) -> TurnResult:   # Factor 12: items in, items out
    for _ in range(max_tool_rounds + 1):                                     # Factor 8
        response = client.responses.create(input=messages, tools=RESPONSES_TOOLS, store=False, ...)  # Factor 1
        for call in (o for o in response.output if o.type == "function_call"):
            result = dispatch(store, call.name, args)                        # Factor 4
            messages.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})  # Factor 9
```
