# Foundations

Read before this module. The agent loop, who runs it and why the tools enforce the rules are on the [Build](https://orq-ai.github.io/orq-workshop/build/) stage page. This page is what the managed shape looks like on the wire.

## The entity

The refund agent is one `agents.create` call, simplified from `agent_payload()` in [`app/refund_agent/entities.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/refund_agent/entities.py), which `make seed-workspace` runs:

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

The limits (8 iterations, 120 s) are where the loop stops if the model never answers.

## One tool call, two items

The model asks for `lookup_order`; orq.ai runs the code tool and adds the result. Both land in the same response:

```python
# The model asks for structured work.
{"type": "function_call", "name": "ws-lookup_order", "call_id": "call_1", "arguments": '{"order_id":"ord_a2"}'}

# orq.ai ran the code tool; this item carries its result,
# here {"ok": True, "order": {"id": "ord_a2", "amount": 89.0, ...}}.
{"type": "orq:ws-lookup_order", "call_id": "call_1", ...}
```

The refund agent runs this pair up to three times in one turn: `lookup_order`, `get_policy`, `issue_refund`, then the final `message`.

## One turn on the wire

One `responses.create` call is one customer turn. `response.output` holds every `function_call`, its matching `orq:<tool>` result and the final `message`; `telemetry.trace_id` points at the trace. Match call and result on `call_id`, not `id`.

`agent/<key>` runs the latest version; `agent/<key>@1.0.0` pins one.

With a **function tool** instead, orq.ai stops at the `function_call` and your code runs the tool, then continues with `previous_response_id`. That is step 2b of the module, and it is how a tool that touches your own systems stays in your process.

## Next

The [Use case](https://orq-ai.github.io/orq-workshop/modules/managed-agents/logic/) states the refund requirements, the [Agent design](https://orq-ai.github.io/orq-workshop/modules/managed-agents/solution-design/) turns them into prompt and tools, then [Build the agent](https://orq-ai.github.io/orq-workshop/modules/managed-agents/).

## Official docs

- [Build agents](https://docs.orq.ai/ai-studio/ai-engineering/build-agents)
- [Create tools](https://docs.orq.ai/ai-studio/ai-engineering/create-tools)
- [Run agents](https://docs.orq.ai/ai-studio/ai-engineering/run-agents)
- [Responses API](https://docs.orq.ai/ai-gateway/features/responses-api)
