"""Module 15 starter: advisor and sidekick, second-model delegation inside a managed agent.

The agent ws-refund-agent-delegating already exists (make seed): the refund agent on gpt-5.6-luna plus an
`advisor` tool on gpt-5.6-sol and a `sidekick` tool on gpt-5.4-nano. Your job: run it, read what each tool
sent and got back, and read the cost of each choice off the trace.
"""

from __future__ import annotations

import json
from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent-delegating")  # ws-refund-agent-delegating
QUESTION = "Refund ord_a6 please, the frame arrived scratched."  # EUR 620, above the limit: a refusal is coming
orq = make_orq()


def step_1_inspect() -> None:
    a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
    print(f"[1] {a['key']} v{a['version']} model={a['model']['id']}")
    for t in a["settings"]["tools"]:
        if t["action_type"] in ("advisor", "sidekick"):
            print(f"    {t['action_type']:<9} configuration={t.get('configuration')}")


def run_agent(
    agent: str, text: str, *, store: OrderStore | None = None, max_steps: int = 8, **kw: Any
) -> dict[str, Any]:
    """Module 08's loop, plus `items`: every output item of the chain, so step 3 can read the delegation."""
    store = store or OrderStore()
    r = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    traces, called, items = [r["telemetry"]["trace_id"]], [], list(r["output"])
    for _ in range(max_steps):
        done_by_server = {o.get("call_id") for o in r["output"] if o["type"].startswith("orq:")}
        calls = [
            o
            for o in r["output"]
            if o["type"] == "function_call" and o["call_id"] not in done_by_server
        ]
        if not calls:
            break
        outputs = []
        for c in calls:
            result = dispatch(store, c["name"], json.loads(c["arguments"] or "{}"))
            called.append(c["name"])
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": c["call_id"],
                    "output": json.dumps(result),
                }
            )
        r = orq.responses.create(
            model=f"agent/{agent}", previous_response_id=r["id"], input=outputs, **kw
        ).model_dump(by_alias=True)
        traces.append(r["telemetry"]["trace_id"])
        items += r["output"]
    text_out = " ".join(
        c["text"]
        for o in r["output"]
        if o["type"] == "message"
        for c in o["content"]
        if c["type"] == "output_text"
    )
    return {"text": text_out, "tool_calls": called, "traces": traces, "items": items}


def step_2_run() -> dict[str, Any]:
    out = run_agent(AGENT, QUESTION)
    delegated = [
        o["type"][4:] for o in out["items"] if o["type"] in ("orq:advisor", "orq:sidekick")
    ]
    print(f"[2] tools={out['tool_calls']} delegated={delegated} steps={len(out['traces'])}")
    print(f"    answer: {out['text'][:160]}")
    return out


def step_3_read_delegation(out: dict[str, Any]) -> None:
    # TODO: for every orq:advisor / orq:sidekick item, print the arguments of the function_call with the same
    #       call_id (the advisor's `question`, the sidekick's `task`) and the item's `result`
    print("[3] delegation: TODO")


def step_4_cost_split(out: dict[str, Any]) -> None:
    # TODO: orq.traces.list_spans(trace_id=) for each trace; a cost span whose parent is a span.tool named
    #       advisor or sidekick belongs to that tool, the rest to the agent; skip the root (type "trace").
    #       Print cost and share per owner.
    print("[4] cost split: TODO")


def step_5_broken_advisor() -> None:
    # TODO: ensure_delegating_agent(name="refund-agent-delegating-broken", advisor_model="openai/gpt-does-not-exist")
    #       run it and show that the turn still answers; print the orq:advisor result and the advisor span status
    print("[5] broken advisor: TODO")


if __name__ == "__main__":
    step_1_inspect()
    out = step_2_run()
    step_3_read_delegation(out)
    step_4_cost_split(out)
    step_5_broken_advisor()
