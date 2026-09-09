"""Module 09 starter: the refund policy as a knowledge base.

The KB ws-refund-policy exists (make seed). Fill in the searches, then swap get_policy for a KB search.
"""

from __future__ import annotations

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import DATA_DIR, settings

orq = make_orq()
QUERY = "opened electronics after 20 days, can I return?"
KB_KEY = settings.key("refund-policy")   # ws-refund-policy, looked up by key


def kb_id(key: str) -> str:
    return next(k.id for k in orq.knowledge.list(limit=100).data if k.key == key)


def step_1_inspect() -> None:
    kid = kb_id(settings.key("refund-policy"))
    kb = orq.knowledge.retrieve(knowledge_id=kid).model_dump(by_alias=True)
    print(f"[1] {kb['key']} id={kid} model={kb['model']} retrieval={kb['retrieval_settings']}")


def step_2_search(kid: str) -> None:
    for st in ("hybrid_search", "vector_search", "keyword_search"):
        # TODO: orq.knowledge.search(knowledge_id=kid, query=QUERY, top_k=3, search_type=st,
        #                            search_options={"include_scores": True, "include_metadata": True})
        matches = []
        print(f"[2] {st:<15} {len(matches)} matches")


def step_3_chunking() -> None:
    text = (DATA_DIR / "kb" / "post_window_exceptions.md").read_text()
    # TODO: orq.chunking.parse(request={"text": text, "strategy": "sentence", ...}) and "semantic" (needs embedding_model)
    print(f"[3] {len(text)} chars, chunk counts: TODO")


def step_4_policy_from_kb(kid: str) -> None:
    def kb_policy(topic: str) -> dict:
        # TODO: search the KB for the topic and return {"ok": True, "topic": topic, "text": ..., "source": "kb"}
        return {"ok": False, "error": "TODO"}

    r = chat("Refund ord_a3 please, I changed my mind.", policy_fn=kb_policy)
    print(f"[4] tools={r.tool_calls} trace={r.trace_id} answer={r.text[:80]!r}")


if __name__ == "__main__":
    step_1_inspect()
    kid = kb_id(KB_KEY)
    step_2_search(kid)
    step_3_chunking()
    step_4_policy_from_kb(kid)
