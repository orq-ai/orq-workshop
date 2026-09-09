# 01 · Gateway

!!! abstract "Factor 1: Natural language to tool calls, and Factor 8: Own your control flow"
    The model turns "refund ord_a2" into a `lookup_order` call. The gateway turns "the provider is down" into a fallback, without a line of app code. Both are structured decisions you can read in a trace.

**Time:** 25 min · **Prereqs:** module 00 · **You will have:** fallbacks, retry, cache and load balancing on the refund agent, each visible as a span.

## Why

Most teams start with orq as a proxy: point the OpenAI SDK at `https://my.orq.ai/v3/router` and every call is traced. This module shows that the same request body also carries resilience and cost controls. The app stays a plain OpenAI client; the request grows.

## The one concept to understand first

Everything in this module is a field in `extra_body`. The OpenAI SDK forwards unknown fields untouched, so `fallbacks`, `retry`, `timeout`, `cache`, `load_balancer`, `guardrails`, `plugins` and `orq` travel with the request and the gateway acts on them. The native `orq_ai_sdk` exposes the same fields as arguments on `orq.router.chat.completions.create`.

```python
client.chat.completions.create(
    model="openai/gpt-4.1",
    messages=messages,
    tools=TOOL_SCHEMAS,
    extra_body={
        "timeout":   {"call_timeout": 900},
        "fallbacks": [{"model": "openai/gpt-4.1-nano"}],
        "retry":     {"count": 1, "on_codes": [429, 500, 502, 503, 504]},
        "cache":     {"type": "exact_match", "ttl": 600},
    },
)
```

## Steps

Open `modules/01-gateway/run.py`. Each step is a function with a `TODO` where the `extra_body` goes. The solution is in `solution/run.py`.

### Step 1 · A plain call, and the trace it leaves

```bash
$ uv run python modules/01-gateway/run.py
```

Expected output:

```text
[1] plain          trace=4a15b55dcab1454bca91762831cf3113 tools=['lookup_order', 'get_policy', 'issue_refund']
```

In the Studio you find three traces, one per model call in the tool loop, each with cost and latency. Module 02 nests them under one agent span.

### Step 2 · Force a fallback

Fallbacks trigger on `429`, `500`, `502`, `503`, `504` and on a timeout. An unknown model id does not trigger them: that is a `404` returned before any provider is called. The reliable way to see a fallback in a workshop is a tight `call_timeout` on a slower primary model.

Fill in `step_2_fallback`: primary `openai/gpt-4.1`, `timeout.call_timeout` of 900 ms, fallbacks `openai/gpt-4.1-nano` then your default model.

```text
[2] fallback       trace=66ad033e869d1ecb681814c55e1379cd tools=['lookup_order', 'get_policy']
```

Open the trace. The spans read:

```text
chat gpt-4.1          span.chat_completion   error   1201 ms
chat gpt-4.1-nano     span.chat_completion   ok       706 ms
fallback gpt-4.1-nano span.fallback_selected ok
```

If the primary answered under 900 ms the fallback did not fire. Run it again or lower the timeout.

### Step 3 · Cache an identical request

```text
[3] cache          first=5.02s second=1.07s trace2=25b524ffd24108a83bb835340962003c
```

`exact_match` caches on the full request body, so the second run of the same question with the same tools and system prompt is served from cache. Look at the second trace: the cached span reports zero provider cost. The maximum `ttl` is 259200 seconds.

### Step 4 · Split traffic between two models

`load_balancer` with `weight_based` sends each request to one of the listed models by weight. Four calls, four traces; each span carries the selected model.

```text
[4] load balancer  4 traces, check orq.load_balancer.selected_model on each
```

### Step 5 · The same thing from the CLI

```bash
$ orq chat create --model openai/gpt-4o-mini --messages '[{"role":"user","content":"say ok"}]' --json | jq .choices[0].message.content
"Ok!"
$ orq traces search --from 5m --to now --json | jq '.data[] | {trace_id, name, model, cost: .cost.total}' | head -20
```

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Add a fallback chain and a 600 second exact-match cache to `modules/01-gateway/run.py` without changing `app/`. Run it, then use the orq MCP tools to fetch the spans of the fallback trace and tell me which model actually answered and what it cost.

## Done when

- [ ] A trace with a `span.fallback_selected` span exists in your workspace
- [ ] A second identical request came back faster and the span shows cache usage
- [ ] You can explain why an unknown model id does not fall back
- [ ] `app/` is unchanged (`git status` shows only `modules/01-gateway/run.py`)

## Gotchas

- Every fallback attempt gets the same `call_timeout`. Total worst case is `timeout × (1 + fallbacks)`.
- Reasoning models reject `tools` on `/chat/completions`. Keep the refund agent on a non-reasoning model or move to `/responses`.
- `cache` keys on the exact request. A different `thread` or `metadata` value is a different cache key.
- The load balancer picks per request. With two models and four calls you may see the same model four times.

## New in orq 4.13

Router error envelopes are consistent across providers, so the OpenAI SDK parses every error, and rate-limited requests return `Retry-After`. Incremental streaming (4.11) lowers time to first token on the same endpoint.

## Go further

The native SDK exposes the same fields as arguments, no `extra_body`:

```python
orq.router.chat.completions.create(model=..., messages=..., fallbacks=[{"model": "openai/gpt-4.1-nano"}])
```

Pick one client per code base. Frameworks (LangGraph, Strands, CrewAI) already speak OpenAI, so for them the gateway URL is the integration.
