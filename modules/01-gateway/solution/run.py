# %% [markdown]
# # 01 · Gateway
#
# The refund agent is a plain OpenAI client pointed at `https://my.orq.ai/v3/router`. This module
# never touches the app: every control it adds (fallbacks, retry, cache, load balancing) is a field
# in `extra_body`, and every decision the gateway takes for that field shows up as a span in the
# trace. Four steps: a plain call and its trace, a forced fallback, an exact-match cache hit, and a
# weighted split between two models.
#
# | | |
# |---|---|
# | **Time** | 25 min |
# | **Prerequisites** | module 00 (`make setup`, `make smoke` green) |
# | **You will have** | fallbacks, retry, cache and load balancing on the refund agent, each visible as a span |
#
# This file is both the solution script (`make m01`) and the notebook source
# (`make notebooks` turns it into `modules/01-gateway/notebook.ipynb`). Run the cells top to bottom.

# %%
from __future__ import annotations

import time

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Refund ord_a2 please, the dock does not fit my laptop."
TRACES_URL = f"{settings.base_url}/traces"

# %% [markdown]
# ## Step 1 · A plain call, and the trace it leaves
#
# `chat()` runs the refund agent's tool loop: the model asks for a tool, the app runs it, the
# result goes back, until the model answers in words. Nothing about this call is orq-specific: it
# is the OpenAI SDK pointed at the router URL. The trace id comes back in the `x-orq-trace-id`
# response header, and `chat()` keeps it on the result.

# %%
result = chat(QUESTION)

print("── Step 1 · A plain call ──────────────────────────────")
print(f"question : {QUESTION}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print(f"next     : search the trace id in {TRACES_URL}; expect one model span per round of the tool loop")

# %% [markdown]
# In the Studio you find one span per model call in the loop (three here: two tool calls, then
# the answer), each with cost and latency. Module 02 nests them under one agent span.
#
# ## Step 2 · Force a fallback
#
# Fallbacks trigger on `429`, `500`, `502`, `503`, `504` and on a timeout. An unknown model id does
# **not** trigger them: that is a `404` returned before any provider is called. The reliable way to
# see a fallback is a tight `call_timeout` on a slower primary model: `gpt-5.6-sol` needs 1.8 to
# 3.3 s for a tool-calling turn, so a 1500 ms budget fails it almost every time, and `gpt-5.4-nano`
# (about 1 s) takes over.
#
# **Try it first:** call `chat(QUESTION, model="openai/gpt-5.6-sol", extra_body=...)` with a
# `timeout.call_timeout` of 1500 ms, fallbacks `openai/gpt-5.4-nano` then `settings.model`, and one
# retry on the 5xx codes. Then compare with the cell below.

# %%
PRIMARY = "openai/gpt-5.6-sol"
CALL_TIMEOUT_MS = 1500  # below sol's usual latency, so the timeout fires and the chain starts

result = chat(
    QUESTION,
    model=PRIMARY,
    extra_body={
        "timeout": {"call_timeout": CALL_TIMEOUT_MS},
        "fallbacks": [{"model": "openai/gpt-5.4-nano"}, {"model": settings.model}],
        "retry": {"count": 1, "on_codes": [429, 500, 502, 503, 504]},
    },
)

print("── Step 2 · Force a fallback ──────────────────────────")
print(f"primary  : {PRIMARY}, call_timeout {CALL_TIMEOUT_MS} ms, then gpt-5.4-nano, then {settings.model}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print("next     : in the trace, expect chat gpt-5.6-sol (error, timeout) → retry → fallback gpt-5.4-nano → chat gpt-5.4-nano (ok)")

# %% [markdown]
# Open the trace. The spans read `chat gpt-5.6-sol` (error, timeout), `retry`, the same error
# again, then `span.fallback_selected` and `chat gpt-5.4-nano` (ok). If the primary answered under
# 1500 ms the fallback did not fire: run the cell again or lower the timeout. Nano usually finishes
# the whole turn, refund included: it does not stop to confirm the way luna and sol do.
#
# ## Step 3 · Cache an identical request
#
# `exact_match` caches on the full request body, so the second run of the same question with the
# same tools and system prompt is served from cache. The maximum `ttl` is 259200 seconds (3 days).

# %%
CACHE_QUESTION = "What is your refund window?"
cache_body = {"cache": {"type": "exact_match", "ttl": 600}}

started = time.time()
first = chat(CACHE_QUESTION, extra_body=cache_body)
first_seconds = time.time() - started

started = time.time()
second = chat(CACHE_QUESTION, extra_body=cache_body)
second_seconds = time.time() - started

print("── Step 3 · Cache an identical request ────────────────")
print(f"question : {CACHE_QUESTION}")
print(f"first    : {first_seconds:.2f}s  trace {first.trace_id}")
print(f"second   : {second_seconds:.2f}s  trace {second.trace_id}")
print(f"verdict  : {'second call served from cache' if second_seconds < first_seconds else 'second call was not faster: cache miss? rerun the cell'}")
print("next     : open the second trace; the cached span reports zero provider cost")

# %% [markdown]
# ## Step 4 · Split traffic between two models
#
# `load_balancer` with `weight_based` sends each request to one of the listed models by weight.
# Four calls, four traces; each span carries `orq.load_balancer.selected_model`. With two models
# and four calls you may still see the same model four times: the pick is per request.

# %%
SECOND_MODEL = "openai/gpt-5.6-terra"
balancer_body = {
    "load_balancer": {
        "type": "weight_based",
        "models": [
            {"model": settings.model, "weight": 0.5},
            {"model": SECOND_MODEL, "weight": 0.5},
        ],
    }
}

trace_ids = []
for _ in range(4):
    result = chat("One sentence: can I refund after 30 days?", extra_body=balancer_body)
    trace_ids.append(result.trace_id or "none")  # the header can be missing on an error response

print("── Step 4 · Split traffic between two models ──────────")
print(f"models   : {settings.model} (0.5), {SECOND_MODEL} (0.5)")
print(f"calls    : {len(trace_ids)}")
print(f"traces   : {', '.join(trace_ids)}")
print("next     : open each trace and read orq.load_balancer.selected_model on the model span")

# %% [markdown]
# ## What to take away
#
# - The app did not change. Every control in this module travelled in `extra_body`, and the same
#   fields work on `/chat/completions` and `/responses`.
# - Every gateway decision is a span: `span.retry`, `span.fallback_selected`, the cached span with
#   zero cost, `orq.load_balancer.selected_model`. If you cannot see it in the trace, it did not happen.
# - Fallbacks fire on `429`, `5xx` and timeouts, not on a `404` for an unknown model id.
# - Every fallback attempt gets the same `call_timeout`, so the worst case is
#   `timeout × (1 + fallbacks)`.

# %%
print(f"open {TRACES_URL} and filter by the last minute")
