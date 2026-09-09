"""Module 01 starter: fallbacks, retry, cache and load balancing through the gateway.

Everything is `extra_body`. The app does not change; the request does.
"""

from __future__ import annotations

import time

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."


def step_1_plain() -> None:
    r = chat(QUESTION)
    print(f"[1] plain          trace={r.trace_id} tools={r.tool_calls}")


def step_2_fallback() -> None:
    # Fallbacks trigger on 429/5xx and on a timeout. A tight call_timeout on a slow primary model
    # forces the chain; the trace gets a `fallback_selected` span. Unknown model ids do NOT trigger it (404).
    # TODO: primary openai/gpt-4.1, timeout.call_timeout 900, fallbacks gpt-4.1-nano then settings.model, retry on 429/5xx
    r = chat(QUESTION, model="openai/gpt-4.1", extra_body={})
    print(f"[2] fallback       trace={r.trace_id} tools={r.tool_calls}")


def step_3_cache() -> None:
    body = {}  # TODO: cache exact_match, ttl 600
    t0 = time.time(); r1 = chat("What is your refund window?", extra_body=body); t1 = time.time()
    r2 = chat("What is your refund window?", extra_body=body); t2 = time.time()
    print(f"[3] cache          first={t1 - t0:.2f}s second={t2 - t1:.2f}s trace2={r2.trace_id}")


def step_4_load_balancer() -> None:
    body = {}  # TODO: load_balancer weight_based, two models, weight 0.5 each
    seen = set()
    for _ in range(4):
        r = chat("One sentence: can I refund after 30 days?", extra_body=body)
        seen.add(r.trace_id)
    print(f"[4] load balancer  {len(seen)} traces, check orq.load_balancer.selected_model on each")


if __name__ == "__main__":
    step_1_plain()
    step_2_fallback()
    step_3_cache()
    step_4_load_balancer()
    print(f"open {settings.base_url}/traces and filter by the last minute")
