# 09 · Knowledge base and RAG

!!! abstract "Factor 3: Own your context window, and Factor 13: Pre-fetch context"
    Retrieval decides what the model sees. Chunking decides what retrieval can find. Both are settings you own, and the cheapest RAG is the one that searches before the model call instead of asking the model to search.

**Time:** 35 min · **Prereqs:** modules 00 to 02, `make seed` · **You will have:** the refund policy searched three ways, re-chunked two ways, wired into the local agent in place of `get_policy`, pre-fetched into a plain completion, and searched by a managed agent through its knowledge tools.

## Why

`get_policy(topic)` works because the policy is four short files with known names. Real policy is hundreds of pages that change weekly. A knowledge base turns "which file" into "which chunks match this question", and the same search is available to your code, to the gateway, to managed agents and to the coding-agent skills. This module shows where retrieval can run and what each option puts in the trace.

## The one concept to understand first

A knowledge base is datasources, chunks and one embedding model. Search returns chunks with a score; `search_type` picks vector, keyword or hybrid; `rerank_config` reorders; `agentic_rag_config` lets a model rewrite the query first. What you do with the chunks is the RAG design decision:

```python
matches = orq.knowledge.search(knowledge_id=kb, query=q, top_k=3, search_type="hybrid_search",
                               search_options={"include_scores": True, "include_metadata": True}).matches
context = "\n\n".join(m.text for m in matches)          # Factor 13: fetched before the model call
client.chat.completions.create(model=..., messages=[{"role": "system", "content": f"Answer only from:\n{context}"}, ...])
```

![Diagram: where retrieval runs. One knowledge base, three callers: your code pre-fetches chunks into a system message before a gateway chat call (592 prompt tokens); the gateway can be asked to inject knowledge on a plain chat call but injected nothing here (26 tokens); a managed agent searches through its server tools and the retrieval shows in the trace (3662 tokens).](assets/where-retrieval-runs.png)

## Steps

Open `modules/09-knowledge-base-rag/run.py`. The solution is in `solution/run.py`.

### Step 1 · Inspect the seeded knowledge base

```bash
$ orq knowledge-bases list --json | jq -c '.data[] | select(.key | startswith("ws-")) | {key, id: ._id, model}'
{"key":"ws-refund-policy-large","id":"01M21F3KFRP3NDH9JT87J2QXTV","model":"openai/text-embedding-3-large"}
{"key":"ws-refund-policy","id":"01M21E5BPY4XF0RRC7NS0RQ63D","model":"openai/text-embedding-3-small"}
$ orq knowledge-bases retrieve ws-refund-policy --json | jq -c '{key, id: ._id, model, retrieval_settings}'
{"key":"ws-refund-policy","id":"01M21E5BPY4XF0RRC7NS0RQ63D","model":"openai/text-embedding-3-small","retrieval_settings":{"retrieval_type":"hybrid_search","threshold":0,"top_k":5}}
$ uv run python modules/09-knowledge-base-rag/run.py
```

Expected output (solution, step 1):

```text
[1] ws-refund-policy id=01M21E5BPY4XF0RRC7NS0RQ63D model=openai/text-embedding-3-small retrieval={'retrieval_type': 'hybrid_search', 'top_k': 5, 'threshold': 0.0}
    abuse_patterns.md            chunks=1 status=completed completed=1.0 failed=0.0 queued=0.0
    post_window_exceptions.md    chunks=1 status=completed completed=1.0 failed=0.0 queued=0.0
    refund_basics.md             chunks=1 status=completed completed=1.0 failed=0.0 queued=0.0
    shipping_and_scope.md        chunks=1 status=completed completed=1.0 failed=0.0 queued=0.0
```

One chunk per file: `chunk_size` 300 is in tokens, and each policy file is under 300 tokens. In the Studio open **Knowledge Bases** > `ws-refund-policy` > **Retrieval playground** and type the step 2 query; the same chunks and scores come back.

### Step 2 · Three search modes, with and without a reranker

```text
[2] ws-refund-policy: hybrid_search -> API error occurred: Status 500. Body: {"category":"server","... (vector path broken for this embedding model)
    ws-refund-policy-large (01M21F3KFRP3NDH9JT87J2QXTV):
    hybrid_search   0.654 # Post-window exceptions | 0.619 # Shipping and scope | 0.615 # Refund basics
    vector_search   0.654 # Post-window exceptions | 0.619 # Shipping and scope | 0.615 # Refund basics
    keyword_search  1.000 # Refund basics | 0.501 # Abuse patterns
    + rerank        {'search_score': 0.653556764125824} # Post-window except | {'search_score': 0.6187750101089478} # Shipping and scope | {'search_score': 0.6148313283920288} # Refund basics
    (no rerank_score: no rerank model is enabled in this workspace, so the gateway skipped reranking)
```

Read the first line. The outputs above were captured while `EMBEDDING_MODEL` still defaulted to `openai/text-embedding-3-small`, and in this workspace every vector or hybrid search on a knowledge base embedded with that model returns HTTP 500; keyword search works, and the same documents embedded with `openai/text-embedding-3-large` or `mistral/mistral-embed` search fine. The solution therefore builds `ws-refund-policy-large` (same files, same chunking, `text-embedding-3-large`) and uses it from here on. `.env.example` now ships `EMBEDDING_MODEL=openai/text-embedding-3-large`, so a fresh `make seed` gives you a `ws-refund-policy` that searches on its own; the two knowledge bases are then identical apart from the key. Keyword search finds "return" and "refund" in `refund_basics`; vector search ranks `post_window_exceptions` first because the question is about time; hybrid agrees with vector here. Reranking needs a rerank model enabled under **AI Gateway** > **Models**; without one, `rerank_config` is accepted and ignored and no `rerank_score` appears.

The CLI does the same search:

```bash
$ orq knowledge-bases search ws-refund-policy-large --query "opened electronics after 20 days, can I return?" --search-type hybrid_search --top-k 2 --search-options '{"include_scores": true, "include_metadata": true}' --json | jq -c '.matches[] | {id, scores, metadata, text: .text[:50]}'
{"id":"chunk_01M21F3NBTCN7P36YKJDKS703T","scores":{"search_score":0.653556764125824},"metadata":{"datasource_id":"01M21F3MWW7V7H92CWMRWCE4G4","topic":"post_window_exceptions"},"text":"# Post-window exceptions\n\nRefunds outside the 30-d"}
{"id":"chunk_01M21F3PXMVHR2T5BJQA75C3S9","scores":{"search_score":0.6187750101089478},"metadata":{"datasource_id":"01M21F3PBDHBHD45KYB7QFNQGG","topic":"shipping_and_scope"},"text":"# Shipping and scope\n\nLumen Goods ships from a sin"}
```

`metadata.topic` is the field the seed attached to every chunk; `filter_by={"topic": {"eq": "refund_basics"}}` restricts a search to it.

### Step 3 · Chunking is the lever

`orq.chunking.parse` is a pure function: text in, chunks out, nothing stored. Compare strategies before you rebuild a knowledge base.

```text
[3] post_window_exceptions.md (1034 chars)
    recursive  1 chunks; first='# Post-window exceptions\n\nRefunds outside the 30-day window '
    sentence   3 chunks; first='# Post-window exceptions\n\nRefunds outside the 30-day window '
    semantic   4 chunks; first='# Post-window exceptions\n\nRefunds outside the 30-day window '
```

With one chunk per file, every search returns whole documents and the score is a document score. Sentence chunks (120 tokens) would let "tracking reference format" match the bullet that defines it instead of the whole exceptions page. `semantic` needs an `embedding_model` and splits on topic shifts.

### Step 4 · The local agent reads policy from the knowledge base

`chat(..., policy_fn=...)` swaps `get_policy`'s implementation without touching the tool schema. The model still calls `get_policy(topic)`; the function now searches the knowledge base for the topic and returns the chunks as `text`, `source: "kb"`.

```text
[4] local agent, policy from KB: tools=['lookup_order', 'get_policy'] trace=3ba7758445c646924adb347d334d5b63
    answer: I see that order ord_a3 was delivered 45 days ago, which is beyond the 30-day return window. As such, I'm unable to proc
    the trace still shows only chat spans: knowledge.search is a separate API call, not a span in the gateway trace
```

No retrieval span appears: the gateway traces the model calls it proxies, and `knowledge.search` is a separate API call. To see retrieval inside the trace, either instrument it yourself (module 02, `TRACING=otel`) or let orq run it (steps 5c and 6).

### Step 5 · Pre-fetch the context (Factor 13)

Three ways to put policy in front of the model without a tool round-trip.

```text
[5a] gateway orq.knowledge_bases: prompt_tokens=26 trace=b5c585e4e7b289c9f7a6e59a6687035d
     "Return policies can vary significantly by retailer, so it's essential to consult the specific return"
[5b] pre-fetched in code:          prompt_tokens=592 trace=54bb3fca0c262d5b84b9a193b9697cf0
     'Based on the policy, you are entitled to a refund if:\n\n1. You are the registered owner of the order.\n2. The order was delivered within the last 30 days.\n3. The '
[5c] agent/ws-refund-agent-rag: prompt_tokens=3662 trace=e3c4e4001f3f8787b5b7b74712449189
     output items: ['function_call', 'orq:retrieve_knowledge_bases', 'function_call', 'orq:query_knowledge_base', 'message']
     query='damaged in transit refund policy requirements evidence' -> post_window_exceptions.md score=0.722
     'You cannot return an item that was damaged in transit 45 days after delivery, as requests must be made within a 30-day window. If you have a valid tracking refe'
```

- 5a is the documented gateway feature: `extra_body={"orq": {"knowledge_bases": [{"knowledge_id": ..., "top_k": 3, "search_type": "hybrid_search"}]}}` on a plain `chat.completions` call. In this workspace it injected nothing: 26 prompt tokens, a generic answer, no retrieval span. We tried `orq.knowledge_bases`, top-level `knowledge_bases`, `/v2` and `/v3`, two knowledge bases; a control prompt that must answer `NO CONTEXT` without context answered `NO CONTEXT` every time.
- 5b is five lines of code and works everywhere: search, then a system message. 592 prompt tokens, an answer that quotes the policy.
- 5c is the managed version. A knowledge base attached to an agent is only searched if the agent also has the `retrieve_knowledge_bases` and `query_knowledge_base` server tools. `ws-refund-agent-rag` is a copy of the refund agent with those tools instead of `get_policy`; the `orq:query_knowledge_base` output item carries the query the agent wrote, the chunk, the file name and the score. The seeded `ws-refund-agent` has the knowledge base attached but not the tools, so it never searches it.

### Step 6 · Agentic RAG

```text
[6] agentic_rag_config: 3 matches, response keys are still just 'matches' (the refined query is not exposed)
    0.544 # Shipping and scope | 0.543 # Post-window exceptions | 0.537 # Abuse patterns
```

`agentic_rag_config={"model": ...}` on a search lets a model rewrite a vague query ("my thing broke, what now") before retrieval and grade the results. The response shape does not change, so the rewritten query is not visible here; the Studio knowledge base settings expose the same toggle with a grading strictness.

### Step 7 · An external knowledge base

orq can front a retrieval API you already run. The contract is one endpoint: `POST <api_url>/search` with `{query, top_k, threshold, filter_by, search_options, rerank_config}`, answering `{"matches": [{id, text, metadata, scores: {search_score, rerank_score}}]}`. `solution/external_kb_server.py` serves the four policy files with keyword scoring in 40 lines of `http.server`:

```bash
$ uv run python modules/09-knowledge-base-rag/solution/external_kb_server.py &
$ curl -s -X POST http://127.0.0.1:8765/search -H 'content-type: application/json' -d '{"query":"damaged in transit after 45 days","top_k":2}' | jq -c '.matches[] | {id, scores, metadata}'
{"id":"ext_post_window_exceptions","scores":{"search_score":1.0},"metadata":{"topic":"post_window_exceptions"}}
{"id":"ext_refund_basics","scores":{"search_score":0.5},"metadata":{"topic":"refund_basics"}}
```

Registering it is an instructor demo: `orq knowledge-bases create --key ws-refund-policy-ext --type external --path orq-workshop/workshop --external-config '{"name": "lumen-policy", "api_url": "https://<public-host>", "api_key": "<token>"}'`. orq's servers call `api_url`, so it must be public; a loopback URL cannot work and is not registered here.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the manage-knowledge-base idea with the orq Python SDK (`app.refund_agent.client.make_orq`): write a short policy doc `modules/09-knowledge-base-rag/warranty.md` (Lumen Goods gives a 24-month warranty on tech accessories and 12 months on lighting, claims go through support, not refunds), add it as a new datasource `warranty.md` to the knowledge base `ws-refund-policy-large` using `orq.chunking.parse` (recursive, chunk_size 300, chunk_overlap 40) and `orq.knowledge.create_chunks` with `metadata={"topic": "warranty"}`, poll `orq.knowledge.retrieve_processing_status` until `total_queued` is 0, then run `orq.knowledge.search` for "warranty length" with `search_type="hybrid_search"` and `search_options={"include_scores": True, "include_metadata": True}` and show me the top match with its score and metadata.

## Done when

- [ ] `orq knowledge-bases search ws-refund-policy-large --query "..." --search-type keyword_search` and `vector_search` return different top chunks for the step 2 query
- [ ] You can say why `ws-refund-policy` (the seeded one) returns 500 on hybrid search and what the fix is
- [ ] `run.py` step 4 prints `source: kb` policy in the tool result (add a print in `kb_policy`) and the refund for `ord_a3` is refused
- [ ] Trace `e3c4e4001f3f8787b5b7b74712449189` (or your own from step 5c) shows `orq:query_knowledge_base` with a score in `orq traces thread`
- [ ] The external stub answers `curl` with a `matches` array

## Gotchas

- Vector and hybrid search return `500 internal_error` on a knowledge base embedded with `openai/text-embedding-3-small`; the same chunks with `openai/text-embedding-3-large` search fine. That is why `EMBEDDING_MODEL` defaults to the large model and why this module keeps a second knowledge base. If you inherit a workspace seeded before that change, re-embed: `make reset && make seed`, or keep working against `ws-refund-policy-large`.
- `orq_ai_sdk 4.14.14`: `orq.knowledge.list_datasources` sends `limit=50.0` and the API rejects the float. The solution uses the REST endpoint for that one call. `search_options.include_metadata` shows `metadata.topic` through the CLI and REST; the SDK model drops it.
- All eleven rerank models are `enabled: false` here. `rerank_config` with a disabled model is silently ignored. Enable one under **AI Gateway** > **Models** before you compare.
- `orq knowledge-bases list --json` returns `{data, has_more, object}`, not a bare array: iterate `.data[]`. `ws-refund-policy-large` only appears after the first solution run.
- Gateway-side retrieval (`orq.knowledge_bases` on `chat.completions`) did not inject context in this workspace. Verify with `usage.prompt_tokens` before you trust it, not with the answer text.

## New in orq 4.14

The Chunking API (`orq.chunking.parse`) exposes seven strategies (`token`, `sentence`, `recursive`, `semantic`, `agentic`, `fast`, `late`) as a stateless call, so chunking can be tuned in a script before a datasource is rebuilt. Knowledge base retrieval settings (search type, threshold, top_k, rerank, agentic RAG) can be overridden per request with `retrieval_config`.

## Go further

- `solution/external_kb_server.py`: the `/search` contract in 40 lines. Deploy it behind a public URL and register it with `--type external`.
- Docs: [Knowledge bases](https://docs.orq.ai/docs/ai-studio/ai-engineering/knowledge-bases), [Search API](https://docs.orq.ai/reference/knowledge-bases/search-knowledge-base), [Knowledge bases via AI Gateway](https://docs.orq.ai/docs/ai-gateway/features/knowledge-bases), [External knowledge bases](https://docs.orq.ai/docs/ai-studio/ai-engineering/external-knowledge-bases), [Chunking guide](https://docs.orq.ai/docs/ai-studio/ai-engineering/chunking), [Chunking API](https://docs.orq.ai/reference/chunking/parse-text).
