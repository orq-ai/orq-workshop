# %% [markdown]
# # 09 · Knowledge base and RAG
#
# The refund policy as a knowledge base. `get_policy(topic)` works because the policy is four short files; real policy is hundreds of pages that change weekly. A knowledge base turns "which file" into "which chunks match this question", and the same search serves your code, the gateway, managed agents and the coding-agent skills. Seven steps: inspect the seeded knowledge base, compare three search modes and a reranker, compare chunking strategies, feed the local agent policy from the knowledge base, pre-fetch context three ways, agentic RAG, and the contract for an external knowledge base.
#
# | | |
# |---|---|
# | **Time** | 35 min |
# | **Prerequisites** | modules 00 to 02, `make seed` |
# | **You will have** | the refund policy searched three ways, re-chunked two ways, wired into the local agent in place of `get_policy`, pre-fetched into a plain completion, and searched by a managed agent through its knowledge tools |
#
# This file is both the solution script (`make m09`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
from __future__ import annotations

import json

import httpx

from app.refund_agent.agent import chat
from app.refund_agent.client import make_openai_client, make_orq
from app.refund_agent.config import DATA_DIR, settings

orq = make_orq()
QUERY = "opened electronics after 20 days, can I return?"
KB = settings.key("refund-policy")   # ws-refund-policy, looked up by key (ids change when the seed re-runs)
AGENT = settings.key("refund-agent")  # ws-refund-agent: the seed attaches the KB and the two knowledge server tools


def kb_id(key: str) -> str:
    return next(k.id for k in orq.knowledge.list(limit=100).data if k.key == key)


def search(kid: str, query: str = QUERY, **kw):
    r = orq.knowledge.search(knowledge_id=kid, query=query, top_k=3, search_options={"include_scores": True, "include_metadata": True}, **kw)
    return r.model_dump(by_alias=True)["matches"]

# %% [markdown]
# ## Step 1 · Inspect the seeded knowledge base
#
# `make seed` embedded the four policy files. One chunk per file: `chunk_size` 300 is in tokens and
# each file is under 300 tokens. In the Studio: **Knowledge Bases** > `ws-refund-policy` >
# **Retrieval playground**.
#
# SDK note: `orq.knowledge.list_datasources` sends `limit=50.0` and the API rejects the float
# (4.14.14), so the datasource list is one REST call.

# %%
kid = kb_id(KB)
kb = orq.knowledge.retrieve(knowledge_id=kid).model_dump(by_alias=True)
print(f"[1] {kb['key']} id={kid} model={kb['model']} retrieval={kb['retrieval_settings']}")
ds = httpx.get(f"{settings.base_url}/v2/knowledge/{kid}/datasources", headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30).json()["data"]
for d in ds:
    st = orq.knowledge.retrieve_processing_status(knowledge_id=kid, datasource_id=d["_id"]).model_dump(by_alias=True)
    print(f"    {d['display_name']:<28} chunks={d['chunks_count']} status={d['status']} completed={st['total_completed']} failed={st['total_failed']} queued={st['total_queued']}")

# %% [markdown]
# ## Step 2 · Three search modes, with and without a reranker
#
# Keyword search finds "return" and "refund" in `refund_basics`; vector search ranks
# `post_window_exceptions` first because the question is about time; hybrid usually agrees with
# vector. Reranking needs a rerank model enabled under **AI Gateway** > **Models**; without one,
# `rerank_config` is accepted and ignored and no `rerank_score` appears.

# %%
print(f"[2] {KB} ({kid}):")
for st in ("hybrid_search", "vector_search", "keyword_search"):
    ms = search(kid, search_type=st)
    print(f"    {st:<15} " + " | ".join(f"{m['scores']['search_score']:.3f} {m['text'].splitlines()[0][:26]}" for m in ms))
ms = search(kid, search_type="hybrid_search", rerank_config={"model": "cohere/rerank-multilingual-v3.0", "top_k": 3})
print("    + rerank        " + " | ".join(f"{m['scores']} {m['text'].splitlines()[0][:20]}" for m in ms))
print("    (no rerank_score: no rerank model is enabled in this workspace, so the gateway skipped reranking)")

# %% [markdown]
# `metadata.topic` is the field the seed attached to every chunk; `filter_by={"topic": {"eq":
# "refund_basics"}}` restricts a search to it.
#
# ## Step 3 · Chunking is the lever
#
# `orq.chunking.parse` is a pure function: text in, chunks out, nothing stored. Compare strategies
# before you rebuild a knowledge base. With one chunk per file every search returns whole documents;
# sentence chunks would let "tracking reference format" match the bullet that defines it.

# %%
text = (DATA_DIR / "kb" / "post_window_exceptions.md").read_text()
print(f"[3] post_window_exceptions.md ({len(text)} chars)")
for req in (
    {"strategy": "recursive", "chunk_size": 300, "chunk_overlap": 40},
    {"strategy": "sentence", "chunk_size": 120, "chunk_overlap": 0, "min_sentences_per_chunk": 1},
    {"strategy": "semantic", "embedding_model": settings.embedding_model, "chunk_size": 200},
):
    chunks = orq.chunking.parse(request={"text": text, **req}).chunks
    print(f"    {req['strategy']:<10} {len(chunks)} chunks; first={chunks[0].text[:60]!r}")

# %% [markdown]
# ## Step 4 · The local agent reads policy from the knowledge base
#
# `chat(..., policy_fn=...)` swaps `get_policy`'s implementation without touching the tool schema.
# The model still calls `get_policy(topic)`; the function now searches the knowledge base. No
# retrieval span appears in the trace: the gateway traces the model calls it proxies, and
# `knowledge.search` is a separate API call.

# %%
def kb_policy(topic: str) -> dict:
    ms = search(kid, query=topic.replace("_", " "), search_type="hybrid_search")
    return {"ok": True, "topic": topic, "text": "\n\n".join(m["text"] for m in ms), "source": "kb", "scores": [round(m["scores"]["search_score"], 3) for m in ms]}


r = chat("Refund ord_a3 please, I changed my mind.", policy_fn=kb_policy)
print(f"[4] local agent, policy from KB: tools={r.tool_calls} trace={r.trace_id}")
print(f"    answer: {r.text[:120]}")
print("    the trace still shows only chat spans: knowledge.search is a separate API call, not a span in the gateway trace")

# %% [markdown]
# ## Step 5 · Pre-fetch the context (Factor 13)
#
# Three ways to put policy in front of the model without a tool round-trip.
#
# (a) The documented gateway feature: `orq.knowledge_bases` on a plain `chat.completions` call. In
# this workspace it injected nothing (compare `prompt_tokens` with 5b), so verify with token counts
# before you trust it.
# (b) Five lines of code that work everywhere: search, then a system message.

# %%
client = make_openai_client()
q = "I opened my electronics 20 days ago, can I still return them? Quote the policy."
raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[{"role": "user", "content": q}],
    extra_body={"orq": {"knowledge_bases": [{"knowledge_id": kid, "top_k": 3, "search_type": "hybrid_search"}]}})
p = raw.parse()
print(f"[5a] gateway orq.knowledge_bases: prompt_tokens={p.usage.prompt_tokens} trace={raw.headers.get('x-orq-trace-id')}")
print(f"     {p.choices[0].message.content[:100]!r}")

ctx = "\n\n".join(m["text"] for m in search(kid, query=q, search_type="hybrid_search"))
raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[
    {"role": "system", "content": f"Answer only from this policy:\n\n{ctx}"}, {"role": "user", "content": q}])
p = raw.parse()
print(f"[5b] pre-fetched in code:          prompt_tokens={p.usage.prompt_tokens} trace={raw.headers.get('x-orq-trace-id')}")
print(f"     {p.choices[0].message.content[:160]!r}")

# %% [markdown]
# (c) The managed version. A knowledge base attached to an agent is only searched if the agent also
# has the `retrieve_knowledge_bases` and `query_knowledge_base` server tools; the seed gives
# `ws-refund-agent` both. The `orq:query_knowledge_base` output item carries the query the agent
# wrote, the chunk, the file name and the score.

# %%
r = orq.responses.create(model=f"agent/{AGENT}", input="Can I return an item that was damaged in transit 45 days after delivery? What evidence do you need?").model_dump(by_alias=True)
print(f"[5c] agent/{AGENT}: prompt_tokens={r['usage']['input_tokens']} trace={r['telemetry']['trace_id']}")
print(f"     output items: {[o['type'] for o in r['output']]}")
for o in r["output"]:
    if o["type"] == "orq:query_knowledge_base":
        hit = o["result"][0]
        print(f"     query={json.loads(o['arguments'])['query']!r} -> {hit['file_name']} score={hit['score']:.3f}")
print(f"     {' '.join(c['text'] for o in r['output'] if o['type'] == 'message' for c in o['content'])[:160]!r}")

# %% [markdown]
# ## Step 6 · Agentic RAG
#
# `agentic_rag_config={"model": ...}` lets a model rewrite a vague query before retrieval and grade
# the results. The response shape does not change, so the rewritten query is not visible here; the
# Studio knowledge base settings expose the same toggle with a grading strictness.

# %%
ms = search(kid, query="my thing broke, what now", search_type="hybrid_search", agentic_rag_config={"model": settings.model})
print(f"[6] agentic_rag_config: {len(ms)} matches, response keys are still just 'matches' (the refined query is not exposed)")
print("    " + " | ".join(f"{m['scores']['search_score']:.3f} {m['text'].splitlines()[0][:26]}" for m in ms))

# %% [markdown]
# ## Step 7 · An external knowledge base
#
# orq can front a retrieval API you already run. The contract is one endpoint:
# orq POSTs `{query, top_k, threshold, filter_by, search_options, rerank_config}` to `api_url`,
# answering `{"matches": [{id, text, metadata, scores: {search_score, rerank_score}}]}`, Bearer `api_key`.
# `app/edge.py` implements it over the four policy files with keyword scoring (the same process
# receives module 14's webhooks). orq's servers call `api_url`, so it must be public: `make edge`
# behind `npx localtunnel --port 8001`, or the instance the room shares, as `WS_EDGE_URL`.

# %%
from app.refund_agent.entities import ensure_external_knowledge_base

if settings.edge_url:
    ext = ensure_external_knowledge_base(orq, api_url=settings.edge_url, api_key=settings.webhook_secret)
    ms = search(ext, query="damaged in transit after 45 days")
    print(f"[7] external KB {settings.key('refund-policy-ext')} {ext} -> {settings.edge_url}/search: {len(ms)} matches")
    for m in ms:
        print(f"    {m['scores']['search_score']:.3f} {m['id']:28} {m['text'].splitlines()[0][:50]}")
    print(f"    the same search from the CLI: orq knowledge-bases search {ext} --query 'damaged in transit after 45 days' --top-k 2")
else:
    print("[7] external KB: orq POSTs {query, top_k, threshold, filter_by, search_options, rerank_config} to api_url")
    print("    -> {matches: [{id, text, metadata, scores: {search_score, rerank_score}}]}  see app/edge.py")
    print("    set WS_EDGE_URL to a public URL of `make edge` (npx localtunnel --port 8001) and run this step again")
print(f"open {settings.base_url} > Knowledge Bases > {KB} > Retrieval playground, and re-run the query there")
