"""Stretch: delegation inside a managed agent (orq 4.13 advisor and sidekick tools).

A copy of the refund agent, ws-refund-agent-delegating, gets two extra tools:
  advisor   consults a stronger model mid-turn (openai/gpt-4.1), the decision stays with the agent
  sidekick  delegates a discrete writing task to a cheaper model (openai/gpt-4.1-mini)
Both run server-side and show up as nested spans: advisor -> chat gpt-4.1, sidekick -> chat gpt-4.1-mini.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import agent_payload

sys.path.insert(0, str(Path(__file__).parent))
from run import run_agent  # noqa: E402  the same loop as solution/run.py

AGENT = settings.key("refund-agent-delegating")
orq = make_orq()


def ensure_delegating_agent() -> str:
    try:
        orq.agents.retrieve(agent_key=AGENT)
        return AGENT
    except Exception:  # noqa: BLE001
        pass
    kb = next(k.id for k in orq.knowledge.list(limit=100).data if k.key == settings.key("refund-policy"))
    p = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[settings.key("lookup-order"), settings.key("issue-refund"), settings.key("get-policy")])
    p["key"], p["display_name"] = AGENT, "Refund agent (advisor + sidekick)"
    p["instructions"] += (
        "\n\nDelegation:\n"
        "- Before refusing a post-window or above-limit request, ask the advisor whether the refusal is consistent with the policy text you fetched. "
        "Weigh the advice; the decision stays yours.\n"
        "- After any refund decision, delegate writing the two-sentence customer-facing closing note to the sidekick, giving it the decision and the order id. "
        "Return the sidekick's text verbatim as the last paragraph."
    )
    p["settings"]["tool_approval_required"] = "none"
    p["settings"]["tools"] += [
        {"type": "advisor", "configuration": {"model": "openai/gpt-4.1", "max_uses": 2, "max_transcript_tokens": 4000, "max_tokens": 400}},
        {"type": "sidekick", "configuration": {
            "model": "openai/gpt-4.1-mini", "max_uses": 2, "max_tokens": 200,
            "system_prompt": "Write short, warm customer-service closing notes for Lumen Goods. Plain text, no markdown, no internal tool or policy names.",
            "output_format": "Two sentences.",
        }},
    ]
    orq.agents.create(**p)
    print(f"created {AGENT}")
    return AGENT


if __name__ == "__main__":
    agent = ensure_delegating_agent()
    out = run_agent(agent, "Refund ord_a6 please, the frame arrived scratched.")
    print(f"tools={out['tool_calls']} steps={len(out['traces'])}")
    print(f"answer: {out['text'][:300]}")
    for tid in out["traces"]:
        spans = [(s.name, s.type) for s in orq.traces.list_spans(trace_id=tid).data or []]
        if any(n in ("advisor", "sidekick") for n, _ in spans):
            print(f"trace {tid} (advisor + sidekick spans):")
            for name, typ in spans:
                print(f"    {typ:<22} {name}")
            print(f"    $ orq traces thread {tid}")
