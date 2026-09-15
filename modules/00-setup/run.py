"""Module 00 starter: one refund turn through the gateway, spelled out.

Nothing to code in this module: `make smoke` is the exercise, and this file is the same as the
solution. It makes the call without the checks, so you can read the three things every later
module relies on: the answer, the tools the model called, and the trace id the gateway sent back.

Run it with `uv run python modules/00-setup/run.py`.
"""

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Hi, I want a refund for order ord_a1, I changed my mind."

# ── Step 1 · One refund turn, spelled out ──
# `chat()` runs the tool loop: the model asks for a tool, the app runs it locally, the result goes
# back, until the model answers in words. The trace id comes from the x-orq-trace-id header.
result = chat(QUESTION)

print("── Step 1 · One refund turn, spelled out ──────────────")
print(f"question : {QUESTION}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print(f"next     : search the trace id in {settings.base_url}/traces; expect cost, tokens and latency on the model call")
