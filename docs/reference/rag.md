# How retrieval works

A knowledge base answers one question: *which chunks match this query?* Everything else — the model call, the answer, the trace — happens around that. This page explains the machinery so the numbers in [module 09](../modules/09.md) read as evidence rather than magic.

## The pipeline

![Diagram: the retrieval pipeline. Indexing runs once per datasource — chunk, embed, and store the chunk text and its vector together in one index. Searching runs per query against that same index — retrieve by vector, keyword or hybrid, drop results below the threshold, cut to top_k, optionally rerank with its own model and limits, and return the matches with their scores.](../assets/diagrams/rag-pipeline.png)

Indexing happens once, per datasource:

| Stage | What happens | What you control |
|---|---|---|
| **Chunk** | each file is split into passages | strategy (`recursive`, `sentence`, `semantic`, `token`, …), `chunk_size`, `chunk_overlap` |
| **Embed** | each chunk is turned into a vector | `embedding_model`, fixed per knowledge base |
| **Index** | chunk text and vector are stored together, searchable both ways | nothing — this is the platform's job |

Searching happens per query:

| Stage | What happens | What you control |
|---|---|---|
| **Retrieve** | the query is matched against the index | `search_type`: `vector_search`, `keyword_search`, `hybrid_search` |
| **Threshold** | low-scoring chunks are dropped | `threshold`, 0 to 1 |
| **Limit** | the list is cut to size | `top_k` |
| **Rerank** *(optional)* | a rerank model re-scores and re-orders what survived | `rerank_config`: `model`, `top_k`, `threshold` |

The result is `matches[]`, each with `text`, `id`, optional `metadata`, and `scores.search_score` — plus `scores.rerank_score` when a reranker ran.

## The three search modes

![Diagram: one query answered three ways against the same index. Keyword search matches the words themselves, vector search matches meaning through nearest embeddings, and hybrid search runs both and lets the engine fuse the two rankings. A warning below the index notes that a keyword 1.000 and a hybrid 0.654 on the same question are different scales, not a relevance gap.](../assets/diagrams/rag-search-modes.png)

- **`vector_search`** embeds the query and finds the chunks whose vectors sit closest to it. It matches *meaning*: "opened electronics after 20 days" finds a passage about post-window exceptions even though neither phrase appears in it.
- **`keyword_search`** matches the words themselves against the indexed text. It matches *vocabulary*: exact product codes, error strings, policy names — the things an embedding blurs.
- **`hybrid_search`** runs both and the engine fuses the two result lists into one ranking. It is the default, and the right default: most questions are part meaning, part vocabulary.

Chunk text and chunk vector live in the same index, which is why one query can be answered either way without a second system.

### Why the scores are not comparable across modes

This trips people up. A keyword search can return `1.000` while a hybrid search's best hit is `0.654` **for the same query over the same documents**. That is not a relevance difference — it is two different scales. Keyword scores come from a text-match calculation; vector and hybrid scores come from embedding distance. Compare scores *within* one mode, never across modes, and never set a threshold without checking what that mode actually scores.

### Retrieve broadly, return precisely

`top_k` and `rerank_config.top_k` are different dials, and the split is the point: `top_k` decides how many candidates the *retrieval* stage produces, `rerank_config.top_k` decides how many survive *reranking*. Pull 50 candidates cheaply, let a rerank model pick the best 5. A threshold set too high returns nothing at all, which looks identical to an empty knowledge base — check your scores before you tighten it.

### Agentic RAG

`agentic_rag_config` puts a model in front of retrieval: it rewrites a vague query ("my thing broke, what now") into something searchable before the search runs. The response shape does not change, so the rewritten query is not visible in the result — only better matches are.

## Internal and external knowledge bases

![Diagram: internal versus external knowledge bases. With an internal base orq chunks, embeds and searches your documents; with an external one you do all three behind your own endpoint and orq stores no chunks and no vectors. Either way orq applies the same tail — top_k, threshold, rerank, rerank threshold — so both return matches in the same shape.](../assets/diagrams/rag-internal-external.png)

An **internal** knowledge base stores your documents: orq chunks, embeds and indexes them. An **external** one stores nothing — you register an HTTPS endpoint and orq calls it. The division of labour:

| Concern | Internal | External |
|---|---|---|
| chunking, embedding, storage | orq, via `embedding_model` | **yours** — orq holds no chunks and no vectors |
| the search itself | orq: `vector_search` / `keyword_search` / `hybrid_search` | **yours** — an external base has no `retrieval_type`; your endpoint decides how to search |
| `top_k`, `threshold` | orq applies them | sent to you in the request **and** re-applied by orq to what you return |
| rerank | orq, via `rerank_config` | **orq**, on the results you returned |
| auth | your workspace API key | `Authorization: Bearer <api_key>`, stored encrypted |
| transport | inside the platform | public HTTPS — orq calls you, so the endpoint must be reachable |

The row worth dwelling on is rerank. Going external does **not** mean giving up orq's ranking: after your endpoint answers, orq applies the same tail it applies internally — cut to `top_k`, filter by `threshold`, rerank, filter by the rerank threshold. You own retrieval; the platform still owns ranking discipline. Reranking can also be called on its own, so candidates from a vector database you already run can be ordered by orq without registering anything.

Internal and external are therefore not a binary. Between them sit useful mixtures: your store with orq's reranking, or orq's store with your chunking done up front through the chunking API.

### The external contract

orq POSTs to your `api_url` with `Authorization: Bearer <api_key>`:

```json
{
  "query": "damaged in transit after 45 days",
  "top_k": 50,
  "threshold": 0.5,
  "filter_by": {},
  "search_options": { "include_vectors": true, "include_metadata": true, "include_scores": true },
  "rerank_config": { "model": "cohere/rerank-multilingual-v3.0", "threshold": 0, "top_k": 10 }
}
```

and expects the same shape a knowledge base search returns:

```json
{
  "matches": [
    { "id": "…", "text": "…", "metadata": {}, "scores": { "search_score": 0.75, "rerank_score": 0.9 } }
  ]
}
```

Scores belong in 0 to 1, because orq's threshold filter compares against them directly. `filter_by`, `search_options` and `rerank_config` are forwarded to you: implement what you can, ignore the rest.

What happens when your endpoint misbehaves is worth knowing before a demo:

| Situation | What the caller sees |
|---|---|
| your endpoint takes longer than 50 seconds | `504`, the request is aborted |
| your endpoint returns a non-2xx | that same status, passed through |
| unreachable, TLS failure, bad JSON | `502` |

## Where retrieval can run

The same knowledge base is reachable from four places, and the choice decides what appears in the trace:

| Shape | Retrieval runs in | Trace shows |
|---|---|---|
| **Search, then prompt** — search in your code, put the chunks in a system message | your process | the model call only |
| **Retrieval as a tool** — the model calls a tool your loop executes | your process | the model calls; the search is a separate API call |
| **Managed agent** — the agent holds the knowledge base and the built-in knowledge tools | orq | the retrieval, as its own item and span |
| **External base** — any of the above, but the search is your endpoint | your service, called by orq | depends on the shape above it |

[Module 09](../modules/09.md) runs all four against the same four policy files and prints the prompt-token count for each, which is the cheapest way to see what actually reached the model.

## Related

- [Module 09 · Knowledge base and RAG](../modules/09.md) — the hands-on version
- [Glossary](glossary.md) — one-line definitions
- [orq docs · Knowledge bases](https://docs.orq.ai/docs/ai-studio/ai-engineering/knowledge-bases)
- [orq docs · External knowledge bases](https://docs.orq.ai/docs/ai-studio/ai-engineering/external-knowledge-bases)
- [orq docs · Search API](https://docs.orq.ai/reference/knowledge-bases/search-knowledge-base)
