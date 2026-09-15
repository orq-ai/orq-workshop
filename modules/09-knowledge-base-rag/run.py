"""Module 09 starter: the refund policy as a knowledge base.

`get_policy(topic)` works because the policy is four short files. A knowledge base turns
"which file" into "which chunks match this question". The KB `ws-refund-policy` already
exists (`make seed`). Fill in the searches, compare chunking strategies, then swap
`get_policy` for a knowledge base search without touching the tool schema.

Fill in the TODOs. The script runs as is; a step with an empty body prints what is missing.
Run it with `uv run python modules/09-knowledge-base-rag/run.py`. The solution is in `solution/run.py`.
"""

from __future__ import annotations

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import DATA_DIR, settings

orq = make_orq()
QUERY = "opened electronics after 20 days, can I return?"
KB_KEY = settings.key("refund-policy")  # ws-refund-policy; ids change when the seed re-runs, keys do not


def knowledge_id_for(key: str) -> str:
    """Resolve a knowledge base key to its id: every search call wants the id, not the key."""
    return next(kb.id for kb in orq.knowledge.list(limit=100).data if kb.key == key)


def step_1_inspect(knowledge_id: str) -> None:
    """Read the seeded knowledge base back: embedding model and retrieval settings."""
    knowledge_base = orq.knowledge.retrieve(knowledge_id=knowledge_id).model_dump(by_alias=True)

    print("── Step 1 · Inspect the seeded knowledge base ─────────")
    print(f"kb       : {knowledge_base['key']} ({knowledge_id})")
    print(f"model    : {knowledge_base['model']}")
    print(f"settings : {knowledge_base['retrieval_settings']}")
    print(f"next     : open {settings.base_url} > Knowledge Bases > {KB_KEY} > Retrieval playground")


def step_2_search(knowledge_id: str) -> None:
    """The same question through the three search types; the top chunk differs."""
    print("── Step 2 · Three search modes ────────────────────────")
    print(f"query    : {QUERY}")
    for search_type in ("hybrid_search", "vector_search", "keyword_search"):
        # TODO: orq.knowledge.search(knowledge_id=knowledge_id, query=QUERY, top_k=3, search_type=search_type,
        #                            search_options={"include_scores": True, "include_metadata": True})
        matches = []
        if not matches:
            print(f"TODO     : fill in the {search_type} call, then rerun")
        print(f"{search_type.split('_')[0]:<8} : {len(matches)} matches")
    print("next     : keyword should rank refund_basics first, vector post_window_exceptions")


def step_3_chunking() -> None:
    """orq.chunking.parse is a pure function: compare strategies before rebuilding a datasource."""
    policy_text = (DATA_DIR / "kb" / "post_window_exceptions.md").read_text()
    # TODO: orq.chunking.parse(request={"text": policy_text, "strategy": "sentence", "chunk_size": 120, ...})
    #       and "semantic" (needs "embedding_model": settings.embedding_model); print len(...chunks) for each
    chunk_counts: dict[str, int] = {}

    print("── Step 3 · Chunking is the lever ─────────────────────")
    print(f"file     : post_window_exceptions.md ({len(policy_text)} chars)")
    if not chunk_counts:
        print("TODO     : fill in `chunk_counts` with one orq.chunking.parse call per strategy, then rerun")
    for strategy, count in chunk_counts.items():
        print(f"chunks   : {strategy:<9} {count}")
    print("next     : nothing was stored; pick a strategy, then rebuild the datasource with it")


def step_4_policy_from_kb(knowledge_id: str) -> None:
    """Swap get_policy's implementation for a KB search; the model still calls get_policy(topic)."""

    tool_results: list[dict] = []  # what the model received from get_policy during this turn

    def kb_policy(topic: str) -> dict:
        # TODO: search the KB for the topic and return {"ok": True, "topic": topic, "text": ..., "source": "kb"}
        policy = {"ok": False, "error": "TODO"}
        tool_results.append(policy)
        return policy

    question = "Refund ord_a3 please, I changed my mind."
    result = chat(question, policy_fn=kb_policy)

    print("── Step 4 · The local agent reads policy from the KB ──")
    if not any(policy.get("ok") for policy in tool_results):
        print("TODO     : fill in `kb_policy` with a knowledge search, then rerun")
    print(f"question : {question}")
    print(f"policy   : {', '.join(policy.get('source', 'TODO') for policy in tool_results) or 'get_policy was not called'}")
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")
    print("next     : the trace shows only chat spans; knowledge.search is a separate API call, not a span")


if __name__ == "__main__":
    knowledge_id = knowledge_id_for(KB_KEY)
    step_1_inspect(knowledge_id)
    step_2_search(knowledge_id)
    step_3_chunking()
    step_4_policy_from_kb(knowledge_id)
