# 01 · Gateway

!!! abstract "Factor 1: Natural language to tool calls, and Factor 8: Own your control flow"
    The model turns "refund ord_a2" into a `lookup_order` call. The gateway turns "the provider is down" into a fallback, without a line of app code. Both are structured decisions you can read in a trace.

| | |
|---|---|
| **Time** | 25 min |
| **Prerequisites** | module 00 |
| **You will have** | fallbacks, retry, cache and load balancing on the refund agent, each visible as a span. |

## Why

Most teams start with orq as a proxy: point the OpenAI SDK at `https://my.orq.ai/v3/router` and every call is traced. This module shows that the same request body also carries resilience and cost controls. The app stays a plain OpenAI client; the request grows.

## The one concept to understand first

Everything in this module is a field in `extra_body` ([retries and fallbacks](https://docs.orq.ai/docs/ai-gateway/features/retries), [timeouts](https://docs.orq.ai/docs/ai-gateway/features/timeouts), [cache](https://docs.orq.ai/docs/ai-gateway/features/cache), [load balancing](https://docs.orq.ai/docs/ai-gateway/features/load-balancing)). The OpenAI SDK forwards unknown fields untouched, so `fallbacks`, `retry`, `timeout`, `cache`, `load_balancer`, `guardrails`, `plugins` and `orq` travel with the request and the gateway acts on them. The same fields work on `/chat/completions` and on `/responses`; the app uses the latter.

```python
client.responses.create(
    model="openai/gpt-5.6-sol",
    instructions=INSTRUCTIONS, input=messages,
    tools=RESPONSES_TOOLS, store=False,
    extra_body={
        "timeout":   {"call_timeout": 1500},
        "fallbacks": [{"model": "openai/gpt-5.4-nano"}],
        "retry":     {"count": 1, "on_codes": [429, 500, 502, 503, 504]},
        "cache":     {"type": "exact_match", "ttl": 600},
    },
)
```

![Diagram: the fallback chain as a sequence. The refund app sends a Responses call with timeout, fallbacks, retry and cache in extra_body; the gateway calls gpt-5.6-sol, which times out after 1500 ms, retries once, records a span.fallback_selected, calls gpt-5.4-nano, which answers in about 1100 ms, and returns the response to the app. The same request again within the ttl is a cache hit with zero provider cost.](assets/fallback-chain.png)

## Steps

Open `modules/01-gateway/run.py`. Each step is a function with a `TODO` where the `extra_body` goes. The solution is in `solution/run.py`.

### Step 1 · A plain call, and the trace it leaves

```bash
$ uv run python modules/01-gateway/run.py
```

Expected output:

```text
── Step 1 · A plain call ──────────────────────────────
question : Refund ord_a2 please, the dock does not fit my laptop.
answer   : Your refund of **€89** for order **ord_a2** has been issued to the original payment method. It shoul…
tools    : lookup_order → get_policy → issue_refund
trace    : c1ffc319ff931393bb52d3e50d24e7f6
next     : search the trace id in https://my.orq.ai/traces; expect one model span per round of the tool loop
```

`tools` is the order the model called them: it looked the order up, checked the policy, then issued the refund. In the Studio you find one span per model call in the tool loop (four here: three tool calls, then the answer), each with cost and latency. Module 02 nests them under one agent span.

### Step 2 · Force a fallback

Fallbacks trigger on `429`, `500`, `502`, `503`, `504` and on a timeout. An unknown model id does not trigger them: that is a `404` returned before any provider is called. The reliable way to see a fallback in a workshop is a tight `call_timeout` on a slower primary model.

Fill in `step_2_fallback`: primary `openai/gpt-5.6-sol`, `timeout.call_timeout` of 1500 ms, fallbacks `openai/gpt-5.4-nano` then your default model.

```text
── Step 2 · Force a fallback ──────────────────────────
primary  : openai/gpt-5.6-sol, call_timeout 1500 ms, then gpt-5.4-nano, then openai/gpt-5.6-luna
answer   : Your refund of €89 has been issued to the original payment method. It should arrive within 5–7 busin…
tools    : lookup_order → get_policy → issue_refund
trace    : c3340b63763b85dad14bb82b470e26b8
next     : in the trace, expect chat gpt-5.6-sol (error, timeout) → retry → fallback gpt-5.4-nano → chat gpt-5.4-nano (ok)
```

Open the trace. The spans read:

```text
chat openai/gpt-5.6-sol    span.responses          error   1502 ms
retry gpt-5.6-sol          span.retry              ok
chat openai/gpt-5.6-sol    span.responses          error   1502 ms
fallback gpt-5.4-nano      span.fallback_selected  ok
chat openai/gpt-5.4-nano   span.responses          ok      1115 ms
```

Two failed attempts on the primary: the `retry` you asked for, then the fallback. If sol answered under 1500 ms the fallback did not fire; run it again or lower the timeout. Nano then finished the whole turn, refund included: it does not stop to confirm the way luna and sol do.

### Step 3 · Cache an identical request

```text
── Step 3 · Cache an identical request ────────────────
question : What is your refund window?
first    : 2.95s  trace ca1e8094619bf349048dd21fc324dfd2
second   : 1.62s  trace a707450029628fa2abe716673a0b2fd8
verdict  : second call served from cache
next     : open the second trace; the cached span reports zero provider cost
```

`exact_match` caches on the full request body, so the second run of the same question with the same tools and system prompt is served from cache. Look at the second trace: the cached span reports zero provider cost. The maximum `ttl` is 259200 seconds.

### Step 4 · Split traffic between two models

`load_balancer` with `weight_based` sends each request to one of the listed models by weight. Four calls, four traces; each span carries the selected model.

```text
── Step 4 · Split traffic between two models ──────────
models   : openai/gpt-5.6-luna (0.5), openai/gpt-5.6-terra (0.5)
calls    : 4
traces   : eb220618454f4093bbb3c6044d8a330b, 8d2bb7afd83f7009652ba27f74e5c562, 06e33d1d9e65f9727b701549165959c7, 7bd4463b4b0f897caa13ed9c4131b6a8
next     : open each trace and read orq.load_balancer.selected_model on the model span
```

### Step 5 · The same thing from the CLI

```console
$ orq chat create --model openai/gpt-5.6-luna --messages '[{"role":"user","content":"say ok"}]' -o json | jq .choices[0].message.content
"Ok!"
$ orq traces search --from 5m --to now -o json | jq '.data[] | {trace_id, name, model, cost: .cost.total}' | head -20
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
- GPT-5.x models reject `tools` on `/chat/completions` unless `reasoning_effort` is `"none"`. The app uses `/responses`, where tools just work; frameworks that still speak chat completions (the LangGraph stretch in module 02) set the flag.
- `cache` keys on the exact request. A different `thread` or `metadata` value is a different cache key.
- The load balancer picks per request. With two models and four calls you may see the same model four times.

## New in orq 4.13

Router error envelopes are consistent across providers, so the OpenAI SDK parses every error, and rate-limited requests return `Retry-After`. Incremental streaming (4.11) lowers time to first token on the same endpoint.

## Go further

The native SDK exposes the same fields as arguments, no `extra_body`:

```python
orq.router.chat.completions.create(model=..., messages=..., fallbacks=[{"model": "openai/gpt-5.4-nano"}])
```

Pick one client per code base. Frameworks (LangGraph, Strands, CrewAI) already speak OpenAI, so for them the gateway URL is the integration.

Docs: [Retries and fallbacks](https://docs.orq.ai/docs/ai-gateway/features/retries), [Timeouts](https://docs.orq.ai/docs/ai-gateway/features/timeouts), [Cache](https://docs.orq.ai/docs/ai-gateway/features/cache), [Load balancing](https://docs.orq.ai/docs/ai-gateway/features/load-balancing), [OpenAI-compatible API](https://docs.orq.ai/docs/ai-gateway/features/openai-compatible-api).
