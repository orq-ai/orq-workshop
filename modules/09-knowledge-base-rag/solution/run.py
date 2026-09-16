# %% [markdown]
# # 09 · Knowledge base and RAG
#
# The refund policy as a knowledge base. `get_policy(topic)` works because the policy is four short
# files; real policy is hundreds of pages that change weekly. A knowledge base turns "which file"
# into "which chunks match this question", and the same search serves your code, the gateway,
# managed agents and the coding-agent skills. Seven steps: inspect the seeded knowledge base,
# compare three search modes and a reranker, compare chunking strategies, feed the local agent
# policy from the knowledge base, pre-fetch context three ways, agentic RAG, and the contract for
# an external knowledge base.
#
# | | |
# |---|---|
# | **Time** | 35 min |
# | **Prerequisites** | modules 00 to 02, `make seed` |
# | **You will have** | the refund policy searched three ways, re-chunked two ways, wired into the local agent in place of `get_policy`, pre-fetched into a plain completion, and searched by a managed agent through its knowledge tools |
#
# This file is both the solution script (`make m09`) and the notebook source
# (`make notebooks` turns it into `modules/09-knowledge-base-rag/notebook.ipynb`). Run the cells top to bottom.

# %%
from __future__ import annotations

import json

import httpx

from app.refund_agent.agent import chat
from app.refund_agent.client import make_openai_client, make_orq
from app.refund_agent.config import DATA_DIR, settings
from app.refund_agent.entities import ensure_external_knowledge_base

orq = make_orq()
QUERY = "opened electronics after 20 days, can I return?"
KB_KEY = settings.key("refund-policy")  # ws-refund-policy; ids change when the seed re-runs, keys do not
AGENT_KEY = settings.key("refund-agent")  # ws-refund-agent: the seed attaches the KB and the two knowledge server tools
STUDIO_KB_URL = f"{settings.base_url} > Knowledge Bases > {KB_KEY}"


def knowledge_id_for(key: str) -> str:
    """Resolve a knowledge base key to its id: every search call wants the id, not the key."""
    return next(kb.id for kb in orq.knowledge.list(limit=100).data if kb.key == key)


def search(knowledge_id: str, query: str = QUERY, **options):
    """One knowledge search with scores and metadata on, as plain dicts; top_k 3 keeps the output short."""
    result = orq.knowledge.search(
        knowledge_id=knowledge_id,
        query=query,
        top_k=3,
        search_options={"include_scores": True, "include_metadata": True},
        **options,
    )
    return result.model_dump(by_alias=True)["matches"]


def first_line(match: dict, width: int = 26) -> str:
    """The chunk's first line (its markdown heading), trimmed: enough to tell the four files apart."""
    return match["text"].splitlines()[0][:width]


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
knowledge_id = knowledge_id_for(KB_KEY)
knowledge_base = orq.knowledge.retrieve(knowledge_id=knowledge_id).model_dump(by_alias=True)
datasources = httpx.get(
    f"{settings.base_url}/v2/knowledge/{knowledge_id}/datasources",
    headers={"Authorization": f"Bearer {settings.api_key}"},
    timeout=30,
).json()["data"]

print("── Step 1 · Inspect the seeded knowledge base ─────────")
print(f"kb       : {knowledge_base['key']} ({knowledge_id})")
print(f"model    : {knowledge_base['model']}")
print(f"settings : {knowledge_base['retrieval_settings']}")
for datasource in datasources:
    status = orq.knowledge.retrieve_processing_status(
        knowledge_id=knowledge_id, datasource_id=datasource["_id"]
    ).model_dump(by_alias=True)
    print(
        f"file     : {datasource['display_name']:<26} chunks={datasource['chunks_count']} "
        f"status={datasource['status']} completed={status['total_completed']:.0f} "
        f"failed={status['total_failed']:.0f} queued={status['total_queued']:.0f}"
    )
print(f"next     : open {STUDIO_KB_URL} > Retrieval playground and type the step 2 query")

# %% [markdown]
# ## Step 2 · Three search modes, with and without a reranker
#
# Keyword search finds "return" and "refund" in `refund_basics`; vector search ranks
# `post_window_exceptions` first because the question is about time; hybrid usually agrees with
# vector. Reranking needs a rerank model enabled under **AI Gateway** > **Models**; without one,
# `rerank_config` is accepted and ignored and no `rerank_score` appears.

# %%
print("── Step 2 · Three search modes, with and without a reranker ──")
print(f"query    : {QUERY}")
for search_type in ("hybrid_search", "vector_search", "keyword_search"):
    matches = search(knowledge_id, search_type=search_type)
    ranking = " | ".join(f"{m['scores']['search_score']:.3f} {first_line(m)}" for m in matches)
    print(f"{search_type.split('_')[0]:<8} : {ranking}")

reranked = search(
    knowledge_id,
    search_type="hybrid_search",
    rerank_config={"model": "cohere/rerank-multilingual-v3.0", "top_k": 3},
)
print("rerank   : " + " | ".join(f"{m['scores']} {first_line(m, 20)}" for m in reranked))
has_rerank_score = any("rerank_score" in m["scores"] for m in reranked)
print(f"verdict  : {'rerank_score present' if has_rerank_score else 'no rerank_score: no rerank model is enabled in this workspace, so the gateway skipped reranking'}")
print("next     : the same search from the CLI: orq knowledge-bases search ws-refund-policy --query '...' --search-type keyword_search")

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
policy_text = (DATA_DIR / "kb" / "post_window_exceptions.md").read_text()
STRATEGIES = [
    {"strategy": "recursive", "chunk_size": 300, "chunk_overlap": 40},  # what the seed used
    {"strategy": "sentence", "chunk_size": 120, "chunk_overlap": 0, "min_sentences_per_chunk": 1},
    {"strategy": "semantic", "embedding_model": settings.embedding_model, "chunk_size": 200},
]

print("── Step 3 · Chunking is the lever ─────────────────────")
print(f"file     : post_window_exceptions.md ({len(policy_text)} chars)")
for strategy in STRATEGIES:
    chunks = orq.chunking.parse(request={"text": policy_text, **strategy}).chunks
    print(f"chunks   : {strategy['strategy']:<9} {len(chunks)}; first={chunks[0].text[:60]!r}")
print("next     : nothing was stored; pick a strategy, then rebuild the datasource with it")

# %% [markdown]
# ## Step 4 · The local agent reads policy from the knowledge base
#
# `chat(..., policy_fn=...)` swaps `get_policy`'s implementation without touching the tool schema.
# The model still calls `get_policy(topic)`; the function now searches the knowledge base. No
# retrieval span appears in the trace: the gateway traces the model calls it proxies, and
# `knowledge.search` is a separate API call.

# %%
def kb_policy(topic: str) -> dict:
    """Drop-in for get_policy: same return shape, but the text comes from a hybrid search on the topic."""
    matches = search(knowledge_id, query=topic.replace("_", " "), search_type="hybrid_search")
    return {
        "ok": True,
        "topic": topic,
        "text": "\n\n".join(m["text"] for m in matches),
        "source": "kb",
        "scores": [round(m["scores"]["search_score"], 3) for m in matches],
    }


REFUND_QUESTION = "Refund ord_a3 please, I changed my mind."
result = chat(REFUND_QUESTION, policy_fn=kb_policy)

print("── Step 4 · The local agent reads policy from the KB ──")
print(f"question : {REFUND_QUESTION}")
print(f"answer   : {result.text[:100]}…")
print(f"tools    : {' → '.join(result.tool_calls)}")
print(f"trace    : {result.trace_id}")
print("next     : the trace shows only chat spans; knowledge.search is a separate API call, not a span in the gateway trace")

# %% [markdown]
# ## Step 5 · Pre-fetch the context
#
# Three ways to put policy in front of the model without a tool round-trip.
#
# (a) The documented gateway feature: `orq.knowledge_bases` on a plain `chat.completions` call. In
# this workspace it injected nothing (compare `prompt_tokens` with 5b), so verify with token counts
# before you trust it.
# (b) Five lines of code that work everywhere: search, then a system message.

# %%
client = make_openai_client()
POLICY_QUESTION = "I opened my electronics 20 days ago, can I still return them? Quote the policy."

gateway_raw = client.chat.completions.with_raw_response.create(
    model=settings.model,
    messages=[{"role": "user", "content": POLICY_QUESTION}],
    extra_body={
        "orq": {
            "knowledge_bases": [
                {"knowledge_id": knowledge_id, "top_k": 3, "search_type": "hybrid_search"}
            ]
        }
    },
)
gateway_completion = gateway_raw.parse()

print("── Step 5a · Gateway-side retrieval (orq.knowledge_bases) ──")
print(f"question : {POLICY_QUESTION}")
print(f"tokens   : prompt_tokens={gateway_completion.usage.prompt_tokens}")
print(f"answer   : {gateway_completion.choices[0].message.content[:100]!r}")
print(f"trace    : {gateway_raw.headers.get('x-orq-trace-id')}")
print("next     : compare prompt_tokens with 5b; a count this low means no policy text was injected")

# %%
context = "\n\n".join(
    m["text"] for m in search(knowledge_id, query=POLICY_QUESTION, search_type="hybrid_search")
)
prefetched_raw = client.chat.completions.with_raw_response.create(
    model=settings.model,
    messages=[
        {"role": "system", "content": f"Answer only from this policy:\n\n{context}"},
        {"role": "user", "content": POLICY_QUESTION},
    ],
)
prefetched_completion = prefetched_raw.parse()

print("── Step 5b · Pre-fetched in code ──────────────────────")
print(f"question : {POLICY_QUESTION}")
print(f"tokens   : prompt_tokens={prefetched_completion.usage.prompt_tokens}")
print(f"answer   : {prefetched_completion.choices[0].message.content[:160]!r}")
print(f"trace    : {prefetched_raw.headers.get('x-orq-trace-id')}")
print("next     : the difference in prompt_tokens is the policy text; that is pre-fetching in five lines")

# %% [markdown]
# (c) The managed version. A knowledge base attached to an agent is only searched if the agent also
# has the `retrieve_knowledge_bases` and `query_knowledge_base` server tools; the seed gives
# `ws-refund-agent` both. The `orq:query_knowledge_base` output item carries the query the agent
# wrote, the chunk, the file name and the score.

# %%
AGENT_QUESTION = "Can I return an item that was damaged in transit 45 days after delivery? What evidence do you need?"
response = orq.responses.create(model=f"agent/{AGENT_KEY}", input=AGENT_QUESTION).model_dump(by_alias=True)
output_items = response["output"]
answer_text = " ".join(
    part["text"] for item in output_items if item["type"] == "message" for part in item["content"]
)

print("── Step 5c · The managed agent searches its own KB ────")
print(f"agent    : agent/{AGENT_KEY}")
print(f"question : {AGENT_QUESTION[:100]}")
print(f"tokens   : input_tokens={response['usage']['input_tokens']}")
print(f"items    : {' → '.join(item['type'] for item in output_items)}")
for item in output_items:
    if item["type"] == "orq:query_knowledge_base":
        top_hit = item["result"][0]
        print(f"search   : {json.loads(item['arguments'])['query']!r} → {top_hit['file_name']} score={top_hit['score']:.3f}")
print(f"answer   : {answer_text[:160]!r}")
print(f"trace    : {response['telemetry']['trace_id']}")
print("next     : the orq:query_knowledge_base item is the retrieval; open the trace to see it as a span")

# %% [markdown]
# ## Step 6 · Agentic RAG
#
# `agentic_rag_config={"model": ...}` lets a model rewrite a vague query before retrieval and grade
# the results. The response shape does not change, so the rewritten query is not visible here; the
# Studio knowledge base settings expose the same toggle with a grading strictness.

# %%
VAGUE_QUERY = "my thing broke, what now"
agentic_matches = search(
    knowledge_id,
    query=VAGUE_QUERY,
    search_type="hybrid_search",
    agentic_rag_config={"model": settings.model},
)

print("── Step 6 · Agentic RAG ───────────────────────────────")
print(f"query    : {VAGUE_QUERY}")
print(f"matches  : {len(agentic_matches)}")
print("ranking  : " + " | ".join(f"{m['scores']['search_score']:.3f} {first_line(m)}" for m in agentic_matches))
print("next     : the response keys are still just 'matches'; the refined query is not exposed by the API")

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
EXTERNAL_QUERY = "damaged in transit after 45 days"

print("── Step 7 · An external knowledge base ────────────────")
if settings.edge_url:
    external_id = ensure_external_knowledge_base(
        orq, api_url=settings.edge_url, api_key=settings.webhook_secret
    )
    external_matches = search(external_id, query=EXTERNAL_QUERY)
    print(f"kb       : {settings.key('refund-policy-ext')} ({external_id}) → {settings.edge_url}/search")
    print(f"query    : {EXTERNAL_QUERY}")
    print(f"matches  : {len(external_matches)}")
    for match in external_matches:
        print(f"match    : {match['scores']['search_score']:.3f} {match['id']:<28} {first_line(match, 50)}")
    print(f"next     : the same search from the CLI: orq knowledge-bases search {external_id} --query '{EXTERNAL_QUERY}' --top-k 2")
else:
    print("skipped  : WS_EDGE_URL is empty, so there is nothing public for orq to call")
    print("contract : orq POSTs {query, top_k, threshold, filter_by, search_options, rerank_config} to api_url")
    print("         : and expects {matches: [{id, text, metadata, scores: {search_score, rerank_score}}]}; see app/edge.py")
    print("next     : run `make edge`, expose it (npx localtunnel --port 8001), put the URL in WS_EDGE_URL and rerun this step")

# %% [markdown]
# ## What to take away
#
# - Search type is a per-request choice: keyword finds words, vector finds meaning, hybrid mixes
#   both. Compare them on your own questions before you pick a default.
# - Chunking decides what retrieval can find. `orq.chunking.parse` lets you compare strategies
#   without rebuilding anything.
# - Where retrieval runs decides what the trace shows: a search in your code is invisible to the
#   gateway; a managed agent's search is an output item and a span.
# - Verify gateway-side injection with `prompt_tokens`, not with the answer text.
# - An external knowledge base is one HTTPS endpoint with a fixed request and response shape.

# %%
print(f"open {STUDIO_KB_URL} > Retrieval playground, and re-run the query there")
