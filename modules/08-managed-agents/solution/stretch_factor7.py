"""Stretch: Factor 7, contact humans with tool calls.

Two mechanisms, one agent copy (ws-refund-agent-approval):
  1. settings.tool_approval_required + tools[].requires_approval. Verified live: on the Responses API path this changes
     nothing for function tools, and even server-side tools with requires_approval=true (current_date) still ran.
     For function tools the approval is yours anyway: the call comes back as a function_call item and nothing happens
     until your code answers it. That is the approval gate. Below it asks before executing issue_refund.
  2. An escalate_to_human function tool the instructions call for above-limit refunds. The tool returns a ticket id,
     so "route to human review" becomes a structured, traceable action instead of a sentence.
"""

from __future__ import annotations

import json

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import agent_payload
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent-approval")
ESCALATE = settings.key("escalate-to-human")
orq = make_orq()


def ensure_escalate_tool() -> str:
    if ESCALATE not in {t.key for t in (orq.tools.list(limit=100).data or []) if getattr(t, "key", None)}:
        orq.tools.create(request={
            "type": "function", "key": ESCALATE, "path": settings.path, "description": "Hand the case to the human review queue.",
            "function": {
                "name": "escalate_to_human",
                "description": "Open a human-review ticket for a refund the agent may not issue itself (above the EUR 500 limit, suspected abuse, disputed evidence). Returns a ticket id.",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "reason": {"type": "string", "description": "Why a human must decide."}}, "required": ["order_id", "reason"]},
            },
        })
        print(f"created tool {ESCALATE}")
    return ESCALATE


def ensure_approval_agent() -> str:
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
    except Exception:  # noqa: BLE001
        pass
    kb = next(k.id for k in orq.knowledge.list(limit=100).data if k.key == settings.key("refund-policy"))
    p = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[])
    p["key"], p["display_name"] = AGENT, "Refund agent (approval + escalation)"
    p["instructions"] += ("\n\nEscalation: when issue_refund returns above_limit_needs_human_review, or you would otherwise route to the human "
                          "review queue, call escalate_to_human(order_id, reason) and give the customer the ticket id.")
    p["settings"]["tool_approval_required"] = "respect_tool"
    p["settings"]["tools"] = tools
    orq.agents.create(**p)
    print(f"created {AGENT}")
    return AGENT


def approve(name: str, args: dict) -> bool:
    """The human gate. Here: auto-approve everything except refunds above EUR 100 (a workshop stand-in for a person)."""
    if name != "issue_refund":
        return True
    amount = OrderStore().orders.get(args.get("order_id", ""), {}).get("amount", 0)
    return amount <= 100


def run(agent: str, text: str) -> None:
    store = OrderStore()
    r = orq.responses.create(model=f"agent/{agent}", input=text).model_dump(by_alias=True)
    for _ in range(8):
        calls = [o for o in r["output"] if o["type"] == "function_call"]
        if not calls:
            break
        outputs = []
        for c in calls:
            args = json.loads(c["arguments"] or "{}")
            if c["name"] == "escalate_to_human":
                result = {"ok": True, "ticket_id": f"HR-{args['order_id']}-0001", "queue": "human_review"}
            elif approve(c["name"], args):
                result = dispatch(store, c["name"], args)
            else:
                result = {"ok": False, "error": "approval_denied_by_human", "next": "escalate_to_human"}
            print(f"    {c['name']}({args}) -> {json.dumps(result)[:80]}")
            outputs.append({"type": "function_call_output", "call_id": c["call_id"], "output": json.dumps(result)})
        r = orq.responses.create(model=f"agent/{agent}", previous_response_id=r["id"], input=outputs).model_dump(by_alias=True)
    text_out = " ".join(c["text"] for o in r["output"] if o["type"] == "message" for c in o["content"])
    print(f"    answer: {text_out[:200]}")
    print(f"    trace: {r['telemetry']['trace_id']}")


if __name__ == "__main__":
    agent = ensure_approval_agent()
    a = orq.agents.retrieve(agent_key=agent).model_dump(by_alias=True)
    print(f"{agent}: tool_approval_required={a['settings']['tool_approval_required']} "
          f"requires_approval={[(t['key'], t['requires_approval']) for t in a['settings']['tools']]}")
    print("[a] in-window, small amount: approved by the gate")
    run(agent, "Refund ord_a1 please, wrong colour.")
    print("[b] above the limit: the tool refuses, the agent escalates")
    run(agent, "Refund ord_a6 please, the frame arrived scratched.")
