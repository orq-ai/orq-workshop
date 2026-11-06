# Agent design

The solution combines a system prompt, policy-backed hosted code tools, and agent settings into one managed orq.ai agent, `ws-refund-agent`.

## The system

A customer message enters the prompt and model. The model requests hosted code tools, receives structured results, and returns a response with a trace. The prompt guides conversation and tool selection. The code tools enforce the business rules. The model can request an action, but a structured tool result determines whether that action succeeded.

## One refund decision

```python
# 1. Check the order exists and belongs to this customer.
order = lookup_order(order_id)
if not order["ok"]:
    return explain("I cannot find that order")

# 2. Delivered more than 30 days ago? Read the exception policy
#    and check the reason and evidence before going further.
if not order["order"]["within_standard_window"]:
    policy = get_policy("post_window_exceptions")
    if not eligible_exception(customer_reason, evidence, policy):
        return route_to_human_review()

# 3. Issue the refund. The tool runs the final checks and says if it worked.
refund = issue_refund(order_id, reason, post_window_exception=exception)
return explain(refund)  # tell the customer what the tool returned
```

The model chooses what to say and which tool to call next. It does not calculate ownership, invent eligibility, or mark an order refunded itself.

## Tool contracts and enforcement

The policy text lives in [`app/data/kb/`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/kb). The tools in [`app/refund_agent/tools.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/refund_agent/tools.py) enforce mechanical checks: ownership, prior refund status, amount, delivery window and allowed exception reasons. The agent assesses the customer's reason and supporting evidence, then chooses whether to request a refund. The tool checks that request against its rules; it does not verify the evidence.

| Tool | What it does |
|---|---|
| `lookup_order` | Finds one of the customer's own orders. Any other order is `not_found`. |
| `get_policy` | Returns the text of one policy topic, such as `refund_basics`. |
| `issue_refund` | Refunds the order, but only if every check below passes. |

`make seed-workspace` turns these functions into orq.ai code tools. In a real storefront `issue_refund` would move money; here it changes a sample order, and every tool call starts from the same fixture orders. It runs its checks in order and stops at the first one that fails:

```python
# issue_refund, simplified from app/refund_agent/tools.py
if not owned(order_id):
    return {"ok": False, "error": "not_found"}
if already_refunded(order_id):
    return {"ok": False, "error": "already_refunded"}
if amount(order_id) > 500:
    return {"ok": False, "error": "above_limit_needs_human_review"}
if outside_30_days(order_id):
    if not post_window_exception:
        return {"ok": False, "error": "outside_window"}
    if reason not in POST_WINDOW_REASONS:
        return {"ok": False, "error": "reason_not_in_exception_list"}
return {"ok": True, "amount_refunded": amount(order_id)}
```

## The instructions

[`app/data/fixed_instructions.md`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/fixed_instructions.md) is the agent's prompt. The tools and the procedure, abridged:

```text
Tools:
- lookup_order(order_id): fetch an order. Returns not found if the session user does not own it.
- get_policy(topic): authoritative policy text. Topics: refund_basics | post_window_exceptions | abuse_patterns | shipping_and_scope
- issue_refund(order_id, reason, post_window_exception=false): issue a refund. The tool enforces ownership, no double refund, the EUR 500 single-refund limit, and the 30-day window unless post_window_exception is true.

Procedure for every refund request:
1. Call lookup_order first. Never refund an order you have not looked up this turn.
2. Call get_policy for the relevant topic. Use only the returned text as policy.
3. In-window, owned, not refunded, at or below the limit: call issue_refund in this turn and state the refunded amount. ...
4. Outside the window: the reason MUST be one of damaged_in_transit, never_received, defective_on_arrival AND the customer must give verifiable evidence (tracking reference, photo, defect timestamp). Refuse if either is missing. No negotiation.
5. Above the limit, already refunded, or not owned: refuse politely and route to the human review queue.
```

The prompt guides what the model chooses; the tools still decide what is allowed. The rest of the file covers confidentiality, customer data and scope.

## Next

[Build the agent](https://orq-ai.github.io/orq-workshop/modules/managed-agents/) creates and invokes this managed agent, then lets you inspect its tool calls and traces.

## Official docs

- [Create tools](https://docs.orq.ai/ai-studio/ai-engineering/create-tools): code-tool contracts and hosted execution
- [Build agents](https://docs.orq.ai/ai-studio/ai-engineering/build-agents): instructions, tools, limits, and versions
- [Run agents](https://docs.orq.ai/ai-studio/ai-engineering/run-agents): managed agent calls through the Responses API
- [Traces](https://docs.orq.ai/ai-studio/observability/traces): inspect model and tool execution
