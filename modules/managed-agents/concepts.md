# Foundations

## The agent loop

An agent is a model with instructions and, optionally, tools. orq.ai runs it in a loop: the model either answers or asks for a tool; orq.ai runs the tool and hands the result back; this repeats until the model answers or hits the agent's limits (`max_iterations` and `max_execution_time`, 8 and 120 s on the refund agent).

The refund agent is one such entity. Simplified from `agent_payload()` in [`app/refund_agent/entities.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/refund_agent/entities.py), which `make seed-workspace` runs:

```python
orq.agents.create(
    key="ws-refund-agent",
    role="Customer-service refund agent for Lumen Goods.",
    instructions=open("app/data/fixed_instructions.md").read(),
    model={"id": "openai/gpt-6-luna", "parameters": {"reasoning_effort": "none"}},
    settings={
        "max_iterations": 8,
        "max_execution_time": 120,
        "tools": [{"type": "code", "key": "ws-lookup_order"}, ...],
    },
)
response = orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please")
```

The instructions tell the model what to do; the model supplies the language. The application sends one input and receives one response.

## One simple tool call

Take `lookup_order`. The model asks for it; orq.ai runs the code tool and returns the result. Both items end up in the same response (abridged):

```python
# The model asks for structured work.
{"type": "function_call", "name": "ws-lookup_order", "call_id": "call_1", "arguments": '{"order_id":"ord_a2"}'}

# orq.ai executes the code tool and adds an item that carries its structured result,
# here {"ok": True, "order": {"id": "ord_a2", "amount": 89.0, ...}}.
{"type": "orq:ws-lookup_order", "call_id": "call_1", ...}
```

The pattern is the loop: **model decision, tool result, model decision, answer**. The refund agent runs it up to three times in one turn: `lookup_order`, `get_policy`, `issue_refund`, then the final `message`.

## One turn on the wire

One `responses.create` call is one customer turn. `response.output` holds every `function_call` item, the matching `orq:<tool>` result and the final `message`; `telemetry.trace_id` points at the trace. Match call and result on `call_id`.

`agent/<key>` always runs the latest version; `agent/<key>@1.0.0` pins one, so the same call gives the same configuration every time.

If the tool is a **function tool** instead, orq.ai stops at the `function_call` and your code runs the tool and continues with `previous_response_id`. That hybrid shape is step 2b of the Build page.

## Next

Apply this generic loop to the [Use case](https://orq-ai.github.io/orq-workshop/modules/managed-agents/logic/). It defines the refund requirements that the [Agent design](https://orq-ai.github.io/orq-workshop/modules/managed-agents/solution-design/) must meet. Then [Build the agent](https://orq-ai.github.io/orq-workshop/modules/managed-agents/).

## Official docs

- [Build agents](https://docs.orq.ai/ai-studio/ai-engineering/build-agents)
- [Create tools](https://docs.orq.ai/ai-studio/ai-engineering/create-tools)
- [Run agents](https://docs.orq.ai/ai-studio/ai-engineering/run-agents)
- [Responses API](https://docs.orq.ai/ai-gateway/features/responses-api)
- [Traces](https://docs.orq.ai/ai-studio/observability/traces)
