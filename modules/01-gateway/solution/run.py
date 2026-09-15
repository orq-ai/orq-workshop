# %% [markdown]
# # 01 · Gateway
#
# Fallbacks, retry, cache and load balancing on the refund agent, through the AI Gateway. The app stays a plain OpenAI client pointed at `https://my.orq.ai/v3/router`; every control here is a field in `extra_body`, and every decision the gateway takes shows up as a span in the trace. Four steps: a plain call and its trace, a forced fallback, an exact-match cache hit, a weighted split between two models.
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

# %% [markdown]
# ## Step 1 · A plain call, and the trace it leaves
#
# `chat()` runs the refund agent's tool loop through the gateway. Nothing about this call is
# orq-specific: it is the OpenAI SDK pointed at `https://my.orq.ai/v3/router`. The trace id comes
# back in the `x-orq-trace-id` response header.

# %%
r = chat(QUESTION)
print(f"[1] plain          trace={r.trace_id} tools={r.tool_calls}")

# %% [markdown]
# In the Studio you find three traces, one per model call in the tool loop, each with cost and
# latency. Module 02 nests them under one agent span.
#
# ## Step 2 · Force a fallback
#
# Fallbacks trigger on `429`, `500`, `502`, `503`, `504` and on a timeout. An unknown model id does
# **not** trigger them: that is a `404` returned before any provider is called. The reliable way to
# see a fallback is a tight `call_timeout` on a slower primary model.
#
# **Try it first:** call `chat(QUESTION, model="openai/gpt-4.1", extra_body=...)` with a
# `timeout.call_timeout` of 900 ms, fallbacks `openai/gpt-4.1-nano` then `settings.model`, and one
# retry on the 5xx codes. Then compare with the cell below.

# %%
r = chat(
    QUESTION,
    model="openai/gpt-4.1",
    extra_body={
        "timeout": {"call_timeout": 900},
        "fallbacks": [{"model": "openai/gpt-4.1-nano"}, {"model": settings.model}],
        "retry": {"count": 1, "on_codes": [429, 500, 502, 503, 504]},
    },
)
print(f"[2] fallback       trace={r.trace_id} tools={r.tool_calls}")

# %% [markdown]
# Open the trace. The spans read `chat gpt-4.1` (error, ~1200 ms), `chat gpt-4.1-nano` (ok), then
# `span.fallback_selected`. If the primary answered under 900 ms the fallback did not fire: run the
# cell again or lower the timeout.
#
# ## Step 3 · Cache an identical request
#
# `exact_match` caches on the full request body, so the second run of the same question with the
# same tools and system prompt is served from cache. The maximum `ttl` is 259200 seconds.

# %%
body = {"cache": {"type": "exact_match", "ttl": 600}}
t0 = time.time(); r1 = chat("What is your refund window?", extra_body=body); t1 = time.time()
r2 = chat("What is your refund window?", extra_body=body); t2 = time.time()
print(f"[3] cache          first={t1 - t0:.2f}s second={t2 - t1:.2f}s trace2={r2.trace_id}")

# %% [markdown]
# Look at the second trace: the cached span reports zero provider cost.
#
# ## Step 4 · Split traffic between two models
#
# `load_balancer` with `weight_based` sends each request to one of the listed models by weight.
# Four calls, four traces; each span carries `orq.load_balancer.selected_model`. With two models
# and four calls you may still see the same model four times: the pick is per request.

# %%
body = {"load_balancer": {"type": "weight_based", "models": [{"model": settings.model, "weight": 0.5}, {"model": "openai/gpt-4.1-mini", "weight": 0.5}]}}
seen = set()
for _ in range(4):
    r = chat("One sentence: can I refund after 30 days?", extra_body=body)
    seen.add(r.trace_id)
print(f"[4] load balancer  {len(seen)} traces, check orq.load_balancer.selected_model on each")

# %% [markdown]
# ## Done when
#
# - A trace with a `span.fallback_selected` span exists in your workspace
# - A second identical request came back faster and the span shows cache usage
# - You can explain why an unknown model id does not fall back
#
# Gotcha to remember: every fallback attempt gets the same `call_timeout`, so the worst case is
# `timeout × (1 + fallbacks)`.

# %%
print(f"open {settings.base_url}/traces and filter by the last minute")
