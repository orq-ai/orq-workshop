# %% [markdown]
# # 08 · Managed agents, stretch: contact humans with tool calls (Factor 7)
#
# Two mechanisms on one agent copy, `ws-refund-agent-approval`:
#
# 1. `settings.tool_approval_required` plus `tools[].requires_approval`. Verified live: on the
#    Responses API path this changes nothing for function tools, and even server-side tools with
#    `requires_approval=true` (`current_date`) still ran. For function tools the approval is yours
#    anyway: the call comes back as a `function_call` item and nothing happens until your code
#    answers it. That is the approval gate. Below it asks before executing `issue_refund`.
# 2. An `escalate_to_human` function tool the instructions call for above-limit refunds. The tool
#    returns a ticket id, so "route to human review" becomes a structured, traceable action instead
#    of a sentence.
#
# Run it with `uv run python modules/08-managed-agents/solution/stretch_factor7.py`.

# %%
from __future__ import annotations

import json

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import agent_payload
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent-approval")
ESCALATE = settings.key("escalate-to-human")
APPROVAL_LIMIT_EUR = 100  # the stand-in human approves refunds up to this amount
orq = make_orq()


def ensure_escalate_tool() -> str:
    """Register the escalate_to_human function tool once. Agents reference tools by key, never inline."""
    if ESCALATE not in {tool.key for tool in (orq.tools.list(limit=100).data or []) if getattr(tool, "key", None)}:
        orq.tools.create(request={
            "type": "function",
            "key": ESCALATE,
            "path": settings.path,
            "description": "Hand the case to the human review queue.",
            "function": {
                "name": "escalate_to_human",
                "description": "Open a human-review ticket for a refund the agent may not issue itself (above the EUR 500 limit, suspected abuse, disputed evidence). Returns a ticket id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "reason": {"type": "string", "description": "Why a human must decide."},
                    },
                    "required": ["order_id", "reason"],
                },
            },
        })
        print(f"created  : tool {ESCALATE}")
    return ESCALATE


def ensure_approval_agent() -> str:
    """Create the approval copy of the refund agent if missing: issue_refund needs approval, escalate_to_human is added."""
    ensure_escalate_tool()
    tools = [
        {"type": "function", "key": settings.key("lookup-order")},
        {"type": "function", "key": settings.key("get-policy")},
        {"type": "function", "key": settings.key("issue-refund"), "requires_approval": True},
        {"type": "function", "key": ESCALATE},
    ]
    try:
        orq.agents.retrieve(agent_key=AGENT)
        return AGENT
    except Exception:  # noqa: BLE001  (not found: create it below)
        pass
    kb = next(knowledge.id for knowledge in orq.knowledge.list(limit=100).data if knowledge.key == settings.key("refund-policy"))
    payload = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[])
    payload["key"] = AGENT
    payload["display_name"] = "Refund agent (approval + escalation)"
    payload["instructions"] += (
        "\n\nEscalation: when issue_refund returns above_limit_needs_human_review, or you would otherwise route to the human "
        "review queue, call escalate_to_human(order_id, reason) and give the customer the ticket id."
    )
    payload["settings"]["tool_approval_required"] = "respect_tool"
    payload["settings"]["tools"] = tools
    orq.agents.create(**payload)
    print(f"created  : agent {AGENT}")
    return AGENT


def approve(name: str, args: dict) -> bool:
    """The human gate. Here: auto-approve everything except refunds above EUR 100 (a workshop stand-in for a person)."""
    if name != "issue_refund":
        return True
    amount = OrderStore().orders.get(args.get("order_id", ""), {}).get("amount", 0)
    return amount <= APPROVAL_LIMIT_EUR


def run(agent: str, text: str) -> None:
    """One customer turn. Every function_call passes the human gate before it runs; escalations get a ticket id."""
    store = OrderStore()
    response = orq.responses.create(model=f"agent/{agent}", input=text).model_dump(by_alias=True)
    for _ in range(8):
        calls = [item for item in response["output"] if item["type"] == "function_call"]
        if not calls:
            break
        outputs = []
        for call in calls:
            args = json.loads(call["arguments"] or "{}")
            if call["name"] == "escalate_to_human":
                result = {"ok": True, "ticket_id": f"HR-{args['order_id']}-0001", "queue": "human_review"}
            elif approve(call["name"], args):
                result = dispatch(store, call["name"], args)
            else:
                result = {"ok": False, "error": "approval_denied_by_human", "next": "escalate_to_human"}
            print(f"call     : {call['name']}({args}) → {json.dumps(result)[:80]}")
            outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)})
        response = orq.responses.create(model=f"agent/{agent}", previous_response_id=response["id"], input=outputs).model_dump(by_alias=True)
    text_out = " ".join(content["text"] for item in response["output"] if item["type"] == "message" for content in item["content"])
    print(f"answer   : {text_out[:200]}")
    print(f"trace    : {response['telemetry']['trace_id']}")

# %% [markdown]
# ## Step 1 · Create the approval agent
#
# The agent is created once and reused. Its read-back settings show the approval flags the API
# stores, even though the Responses path does not act on them for function tools.

# %%
print("── Step 1 · Create the approval agent ─────────────────")
agent = ensure_approval_agent()
agent_info = orq.agents.retrieve(agent_key=agent).model_dump(by_alias=True)

print(f"agent    : {agent}")
print(f"approval : tool_approval_required={agent_info['settings']['tool_approval_required']}")
print(f"tools    : {[(tool['key'], tool['requires_approval']) for tool in agent_info['settings']['tools']]}  (key, requires_approval)")

# %% [markdown]
# ## Step 2 · In-window, small amount
#
# `ord_a1` is under the gate's limit, so `approve` lets `issue_refund` run and the agent confirms.

# %%
print("── Step 2 · In-window, small amount ───────────────────")
print("case     : approved by the gate")
run(agent, "Refund ord_a1 please, wrong colour.")

# %% [markdown]
# ## Step 3 · Above the limit
#
# `ord_a6` is above the EUR 500 limit. The tool refuses, the agent calls `escalate_to_human`, and
# the customer gets a ticket id instead of a promise.

# %%
print("── Step 3 · Above the limit ───────────────────────────")
print("case     : the tool refuses, the agent escalates")
run(agent, "Refund ord_a6 please, the frame arrived scratched.")
print("next     : open the trace; the escalate_to_human call and its ticket id are in the conversation")
