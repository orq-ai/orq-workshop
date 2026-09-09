"""Module 09 solution: the refund policy as a knowledge base.

Factor 3: own your context window. Retrieval decides what the model sees; chunking decides what retrieval can find.
Factor 13: pre-fetch context. Search first, then call the model with the result in the prompt. No tool round-trip.
"""

from __future__ import annotations

import json
import time

from app.refund_agent.agent import chat
from app.refund_agent.client import make_openai_client, make_orq
from app.refund_agent.config import DATA_DIR, settings

orq = make_orq()
QUERY = "opened electronics after 20 days, can I return?"
KB = settings.key("refund-policy")   # ws-refund-policy, looked up by key (ids change when the seed re-runs)
AGENT = settings.key("refund-agent")  # ws-refund-agent: the seed attaches the KB and the two knowledge server tools


def kb_id(key: str) -> str:
    return next(k.id for k in orq.knowledge.list(limit=100).data if k.key == key)



# ---------------------------------------------------------------- step 1: inspect

def step_1_inspect() -> None:
    kid = kb_id(KB)
    kb = orq.knowledge.retrieve(knowledge_id=kid).model_dump(by_alias=True)
    print(f"[1] {kb['key']} id={kid} model={kb['model']} retrieval={kb['retrieval_settings']}")
    # SDK note: orq.knowledge.list_datasources sends limit=50.0 and the API rejects the float (4.14.14). Use the REST call.
    import httpx
    ds = httpx.get(f"{settings.base_url}/v2/knowledge/{kid}/datasources", headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30).json()["data"]
    for d in ds:
        st = orq.knowledge.retrieve_processing_status(knowledge_id=kid, datasource_id=d["_id"]).model_dump(by_alias=True)
        print(f"    {d['display_name']:<28} chunks={d['chunks_count']} status={d['status']} completed={st['total_completed']} failed={st['total_failed']} queued={st['total_queued']}")


# ---------------------------------------------------------------- step 2: search modes

def search(kid: str, query: str = QUERY, **kw):
    r = orq.knowledge.search(knowledge_id=kid, query=query, top_k=3, search_options={"include_scores": True, "include_metadata": True}, **kw)
    return r.model_dump(by_alias=True)["matches"]


def step_2_search() -> str:
    kid = kb_id(KB)
    print(f"[2] {KB} ({kid}):")
    for st in ("hybrid_search", "vector_search", "keyword_search"):
        ms = search(kid, search_type=st)
        print(f"    {st:<15} " + " | ".join(f"{m['scores']['search_score']:.3f} {m['text'].splitlines()[0][:26]}" for m in ms))
    ms = search(kid, search_type="hybrid_search", rerank_config={"model": "cohere/rerank-multilingual-v3.0", "top_k": 3})
    print(f"    + rerank        " + " | ".join(f"{m['scores']} {m['text'].splitlines()[0][:20]}" for m in ms))
    print("    (no rerank_score: no rerank model is enabled in this workspace, so the gateway skipped reranking)")
    return kid


# ---------------------------------------------------------------- step 3: chunking

def step_3_chunking() -> None:
    text = (DATA_DIR / "kb" / "post_window_exceptions.md").read_text()
    print(f"[3] post_window_exceptions.md ({len(text)} chars)")
    for req in (
        {"strategy": "recursive", "chunk_size": 300, "chunk_overlap": 40},
        {"strategy": "sentence", "chunk_size": 120, "chunk_overlap": 0, "min_sentences_per_chunk": 1},
        {"strategy": "semantic", "embedding_model": settings.embedding_model, "chunk_size": 200},
    ):
        chunks = orq.chunking.parse(request={"text": text, **req}).chunks
        print(f"    {req['strategy']:<10} {len(chunks)} chunks; first={chunks[0].text[:60]!r}")


# ---------------------------------------------------------------- step 4: KB instead of get_policy in the local agent

def step_4_policy_from_kb(kid: str) -> None:
    def kb_policy(topic: str) -> dict:
        ms = search(kid, query=topic.replace("_", " "), search_type="hybrid_search")
        return {"ok": True, "topic": topic, "text": "\n\n".join(m["text"] for m in ms), "source": "kb", "scores": [round(m["scores"]["search_score"], 3) for m in ms]}

    r = chat("Refund ord_a3 please, I changed my mind.", policy_fn=kb_policy)
    print(f"[4] local agent, policy from KB: tools={r.tool_calls} trace={r.trace_id}")
    print(f"    answer: {r.text[:120]}")
    print("    the trace still shows only chat spans: knowledge.search is a separate API call, not a span in the gateway trace")


# ---------------------------------------------------------------- step 5: pre-fetch (Factor 13)

def step_5_prefetch(kid: str) -> None:
    client = make_openai_client()
    q = "I opened my electronics 20 days ago, can I still return them? Quote the policy."
    # (a) gateway-side retrieval as documented: orq.knowledge_bases on a plain chat.completions call
    raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[{"role": "user", "content": q}],
        extra_body={"orq": {"knowledge_bases": [{"knowledge_id": kid, "top_k": 3, "search_type": "hybrid_search"}]}})
    p = raw.parse()
    print(f"[5a] gateway orq.knowledge_bases: prompt_tokens={p.usage.prompt_tokens} trace={raw.headers.get('x-orq-trace-id')}")
    print(f"     {p.choices[0].message.content[:100]!r}")
    # (b) pre-fetch in code: search, then put the chunks in the system prompt. Five lines, no tool call.
    ctx = "\n\n".join(m["text"] for m in search(kid, query=q, search_type="hybrid_search"))
    raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[
        {"role": "system", "content": f"Answer only from this policy:\n\n{ctx}"}, {"role": "user", "content": q}])
    p = raw.parse()
    print(f"[5b] pre-fetched in code:          prompt_tokens={p.usage.prompt_tokens} trace={raw.headers.get('x-orq-trace-id')}")
    print(f"     {p.choices[0].message.content[:160]!r}")


def step_5c_managed_retrieval(kid: str) -> None:
    """The seeded agent has the KB attached plus retrieve_knowledge_bases and query_knowledge_base (server tools)."""
    agent = AGENT
    r = orq.responses.create(model=f"agent/{agent}", input="Can I return an item that was damaged in transit 45 days after delivery? What evidence do you need?").model_dump(by_alias=True)
    print(f"[5c] agent/{agent}: prompt_tokens={r['usage']['input_tokens']} trace={r['telemetry']['trace_id']}")
    print(f"     output items: {[o['type'] for o in r['output']]}")
    for o in r["output"]:
        if o["type"] == "orq:query_knowledge_base":
            hit = o["result"][0]
            print(f"     query={json.loads(o['arguments'])['query']!r} -> {hit['file_name']} score={hit['score']:.3f}")
    print(f"     {' '.join(c['text'] for o in r['output'] if o['type'] == 'message' for c in o['content'])[:160]!r}")


# ---------------------------------------------------------------- step 6: agentic RAG

def step_6_agentic(kid: str) -> None:
    ms = search(kid, query="my thing broke, what now", search_type="hybrid_search", agentic_rag_config={"model": settings.model})
    print(f"[6] agentic_rag_config: {len(ms)} matches, response keys are still just 'matches' (the refined query is not exposed)")
    print("    " + " | ".join(f"{m['scores']['search_score']:.3f} {m['text'].splitlines()[0][:26]}" for m in ms))


# ---------------------------------------------------------------- step 7: external knowledge base contract

def step_7_external() -> None:
    print("[7] external KB: POST <api_url>/search {query, top_k, threshold, filter_by, search_options, rerank_config}")
    print("    -> {matches: [{id, text, metadata, scores: {search_score, rerank_score}}]}  see solution/external_kb_server.py")
    print("    register: orq knowledge-bases create --key ws-refund-policy-ext --type external --path orq-workshop/workshop \\")
    print("        --external-config '{\"name\": \"lumen-policy\", \"api_url\": \"https://<public-host>\", \"api_key\": \"<token>\"}'")
    print("    instructor demo only: orq's servers must reach api_url, so a loopback or LAN URL cannot work")


if __name__ == "__main__":
    step_1_inspect()
    kid = step_2_search()
    step_3_chunking()
    step_4_policy_from_kb(kid)
    step_5_prefetch(kid)
    step_5c_managed_retrieval(kid)
    step_6_agentic(kid)
    step_7_external()
    print(f"open {settings.base_url} > Knowledge Bases > {KB} > Retrieval playground, and re-run the query there")
