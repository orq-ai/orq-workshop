# 12-Factor Agents map

[12-Factor Agents](https://github.com/humanlayer/12-factor-agents) by HumanLayer is a set of principles for building LLM software that ships. This workshop uses it as its spine: every module opens with the factor it exercises and the one orq surface that embodies it. The sample app is written that way on purpose.

| Factor | Modules | Where it shows in orq |
|---|---|---|
| 1 · Natural language to tool calls | [01](modules/01.md), [08](modules/08.md) | function calling through the router; `function_call` output items from a managed agent |
| 2 · Own your prompts | [07](modules/07.md), [08](modules/08.md) | instructions as repo files, agent versions, the `optimize-prompt` skill, experiments that compare prompts |
| 3 · Own your context window | [02](modules/02.md), [09](modules/09.md) | traces show the exact context sent; knowledge base `top_k`, threshold and rerank decide what enters |
| 4 · Tools are just structured outputs | [08](modules/08.md), [10](modules/10.md) | the app executes `function_call` items itself; the MCP Gateway exposes a chosen subset of tools |
| 5 · Unify execution state and business state | [02](modules/02.md), [08](modules/08.md) | identity and thread on every call; memory `entity_id`; the order store |
| 6 · Launch, pause, resume with simple APIs | [08](modules/08.md), [12](modules/12.md) | `previous_response_id`, `responses.retrieve`, streaming; headless `orq launch -p` |
| 7 · Contact humans with tool calls | [04](modules/04.md), [08](modules/08.md) | a blocked guardrail as the escalation path; `tool_approval_required`; an `escalate_to_human` tool; annotation queues |
| 8 · Own your control flow | [01](modules/01.md), [04](modules/04.md), [08](modules/08.md) | the loop in `agent.py`; routing rules; guardrail rules; `max_iterations` |
| 9 · Compact errors into the context window | [01](modules/01.md), [07](modules/07.md) | short tool error strings; fallbacks and retry; a failure taxonomy |
| 10 · Small, focused agents | [08](modules/08.md), [10](modules/10.md), [11](modules/11.md) | advisor and sidekick; a gateway that exposes a subset; red teaming shows what a big surface costs |
| 11 · Trigger from anywhere | [02](modules/02.md), [10](modules/10.md), [12](modules/12.md), [13](modules/13.md) | any framework through the gateway; MCP consumers; CI cron; coding agents |
| 12 · Make your agent a stateless reducer | app, [07](modules/07.md), [11](modules/11.md) | `run_turn(messages) -> messages`; evaluatorq `@job`; simulation replay |
| 13 · Pre-fetch all the context you might need | [09](modules/09.md) | gateway-side `knowledge_bases` on a plain chat call; `lookup_order` before the model speaks |

## The app, factor by factor

```python
# app/refund_agent/agent.py
def run_turn(messages, *, store=None, extra_body=None, ...) -> TurnResult:   # Factor 12
    for _ in range(max_tool_rounds + 1):                                     # Factor 8
        completion = client.chat.completions.create(..., tools=TOOL_SCHEMAS)  # Factor 1
        for call in choice.tool_calls:
            result = dispatch(store, call.function.name, args)               # Factor 4
            messages.append({"role": "tool", "content": json.dumps(result)}) # Factor 9
```
