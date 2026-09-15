# %% [markdown]
# # 08 · Managed agents, stretch: delegation inside a managed agent
#
# orq 4.13 added two delegation tools. A copy of the refund agent, `ws-refund-agent-delegating`,
# gets both:
#
# - `advisor` consults a stronger model mid-turn (`openai/gpt-5.6-sol`); the decision stays with the agent.
# - `sidekick` delegates a discrete writing task to a cheaper model (`openai/gpt-5.4-nano`).
#
# Both run server-side and show up as nested spans: `advisor` > `chat gpt-5.6-sol`,
# `sidekick` > `chat gpt-5.4-nano`.
#
# Run it with `uv run python modules/08-managed-agents/solution/stretch_advisor_sidekick.py`. It
# imports `run_agent` from `solution/run.py`, and that import runs the module 08 solution first.

# %%
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
    """Create the delegating copy of the refund agent if missing: same tools plus advisor and sidekick."""
    try:
        orq.agents.retrieve(agent_key=AGENT)
        return AGENT
    except Exception:  # noqa: BLE001  (not found: create it below)
        pass
    kb = next(knowledge.id for knowledge in orq.knowledge.list(limit=100).data if knowledge.key == settings.key("refund-policy"))
    payload = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[settings.key("lookup-order"), settings.key("issue-refund"), settings.key("get-policy")])
    payload["key"] = AGENT
    payload["display_name"] = "Refund agent (advisor + sidekick)"
    payload["instructions"] += (
        "\n\nDelegation:\n"
        "- Before refusing a post-window or above-limit request, ask the advisor whether the refusal is consistent with the policy text you fetched. "
        "Weigh the advice; the decision stays yours.\n"
        "- After any refund decision, delegate writing the two-sentence customer-facing closing note to the sidekick, giving it the decision and the order id. "
        "Return the sidekick's text verbatim as the last paragraph."
    )
    payload["settings"]["tool_approval_required"] = "none"
    payload["settings"]["tools"] += [
        {
            "type": "advisor",
            "configuration": {"model": "openai/gpt-5.6-sol", "max_uses": 2, "max_transcript_tokens": 4000, "max_tokens": 400},
        },
        {
            "type": "sidekick",
            "configuration": {
                "model": "openai/gpt-5.4-nano",
                "max_uses": 2,
                "max_tokens": 200,
                "system_prompt": "Write short, warm customer-service closing notes for Lumen Goods. Plain text, no markdown, no internal tool or policy names.",
                "output_format": "Two sentences.",
            },
        },
    ]
    orq.agents.create(**payload)
    print(f"created  : agent {AGENT}")
    return AGENT

# %% [markdown]
# ## Step 1 · Create the delegating agent
#
# Created once, reused on every run. The advisor and sidekick configurations cap uses and tokens,
# so a delegation loop cannot run away with the bill.

# %%
print("── Step 1 · Create the delegating agent ───────────────")
agent = ensure_delegating_agent()
print(f"agent    : {agent}")

# %% [markdown]
# ## Step 2 · One turn that delegates
#
# `ord_a6` is above the refund limit, so the instructions make the agent consult the advisor before
# refusing and hand the closing note to the sidekick.

# %%
out = run_agent(agent, "Refund ord_a6 please, the frame arrived scratched.")

print("── Step 2 · One turn that delegates ───────────────────")
print(f"tools    : {' → '.join(out['tool_calls'])}")
print(f"requests : {len(out['traces'])}")
print(f"answer   : {out['text'][:300]}")

# %% [markdown]
# ## Step 3 · Find the advisor and sidekick spans
#
# Each Responses call of the turn is its own trace. The one that delegated carries `advisor` and
# `sidekick` spans, each with the nested model call and its own cost.

# %%
print("── Step 3 · Find the advisor and sidekick spans ───────")
for trace_id in out["traces"]:
    spans = [(span.name, span.type) for span in orq.traces.list_spans(trace_id=trace_id).data or []]
    if any(name in ("advisor", "sidekick") for name, _ in spans):
        print(f"trace    : {trace_id} (advisor + sidekick spans)")
        for name, span_type in spans:
            print(f"    {span_type:<22} {name}")
        print(f"next     : run `orq traces thread {trace_id}`")
