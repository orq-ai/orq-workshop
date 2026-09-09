"""Module 00: nothing to code. `make smoke` is the exercise. This file shows the same call, spelled out."""

from app.refund_agent.agent import chat

result = chat("Hi, I want a refund for order ord_a1, I changed my mind.")
print(result.text)
print("tools:", result.tool_calls)
print("trace:", result.trace_id)
