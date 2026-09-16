"""Module 01 starter: fallbacks, retry, cache and load balancing through the gateway.

The app does not change; the request does. Every control in this module is a field in
`extra_body`, and every decision the gateway takes for it becomes a span in the trace.

Fill in the TODOs. The script runs as is; a step with an empty body prints what is missing.
Run it with `uv run python modules/01-gateway/run.py`.
"""

from __future__ import annotations

import time

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."
TRACES_URL = f"{settings.base_url}/traces"


def step_1_plain() -> None:
    """One turn of the refund agent, no gateway controls. The trace id comes from the x-orq-trace-id header."""
    result = chat(QUESTION)

    print("── Step 1 · A plain call ──────────────────────────────")
    print(f"question : {QUESTION}")
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")
    print(f"next     : search the trace id in {TRACES_URL}; expect one model span per round of the tool loop")


def step_2_fallback() -> None:
    """Force the fallback chain with a timeout the primary model cannot meet."""
    # Fallbacks trigger on 429, 5xx and on a timeout. A tight call_timeout on a slow primary model
    # forces the chain and the trace gets a span.fallback_selected. Unknown model ids do NOT trigger
    # it: that is a 404 returned before any provider is called.
    primary = "openai/gpt-5.6-sol"
    body = {}  # TODO: {"timeout": {"call_timeout": 1500}, "fallbacks": [nano, then settings.model], "retry": {"count": 1, "on_codes": [429, 500, 502, 503, 504]}}
    result = chat(QUESTION, model=primary, extra_body=body)

    print("── Step 2 · Force a fallback ──────────────────────────")
    if not body:
        print("TODO     : fill in `body` with timeout, fallbacks and retry, then rerun")
    print(f"primary  : {primary}")
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")
    print("next     : in the trace, expect chat gpt-5.6-sol (error, timeout) → retry → fallback gpt-5.4-nano → chat gpt-5.4-nano (ok)")


def step_3_cache() -> None:
    """Two identical requests; the second one should be served from the gateway cache."""
    question = "What is your refund window?"
    body = {}  # TODO: {"cache": {"type": "exact_match", "ttl": 600}}

    started = time.time()
    first = chat(question, extra_body=body)
    first_seconds = time.time() - started

    started = time.time()
    second = chat(question, extra_body=body)
    second_seconds = time.time() - started

    print("── Step 3 · Cache an identical request ────────────────")
    if not body:
        print("TODO     : fill in `body` with an exact_match cache, then rerun")
    print(f"question : {question}")
    print(f"first    : {first_seconds:.2f}s  trace {first.trace_id}")
    print(f"second   : {second_seconds:.2f}s  trace {second.trace_id}")
    print("next     : open the second trace; the cached span reports zero provider cost")


def step_4_load_balancer() -> None:
    """Four calls split by weight between two models. Each trace records the model the gateway picked."""
    body = {}  # TODO: {"load_balancer": {"type": "weight_based", "models": [{"model": settings.model, "weight": 0.5}, {"model": "openai/gpt-5.6-terra", "weight": 0.5}]}}

    trace_ids = []
    for _ in range(4):
        result = chat("One sentence: can I refund after 30 days?", extra_body=body)
        trace_ids.append(result.trace_id or "none")  # the header can be missing on an error response

    print("── Step 4 · Split traffic between two models ──────────")
    if not body:
        print("TODO     : fill in `body` with a weight_based load balancer, then rerun")
    print(f"calls    : {len(trace_ids)}")
    print(f"traces   : {', '.join(trace_ids)}")
    print("next     : open each trace and read orq.load_balancer.selected_model on the model span")


if __name__ == "__main__":
    step_1_plain()
    step_2_fallback()
    step_3_cache()
    step_4_load_balancer()
    print(f"open {TRACES_URL} and filter by the last minute")
