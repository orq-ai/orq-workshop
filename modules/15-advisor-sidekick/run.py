"""Module 15 starter: advisor and sidekick, second-model delegation inside a managed agent.

One agent on one model runs every step. The `advisor` and `sidekick` tools hand single steps to
a second model configured at design time, each metered on its own span. The agent
`ws-refund-agent-delegating` already exists (`make seed`): the refund agent on gpt-5.6-luna plus
an `advisor` on gpt-5.6-sol and a `sidekick` on gpt-5.4-nano. Your job: run it, read what each
tool sent and got back, and read the cost of each choice off the trace.

Fill in the TODOs. The script runs as is; a step with an empty body prints what is missing.
Run it with `uv run python modules/15-advisor-sidekick/run.py`.
"""

from __future__ import annotations

import json
from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent-delegating")  # ws-refund-agent-delegating
QUESTION = "Refund ord_a6 please, the frame arrived scratched."  # EUR 620, above the limit: a refusal is coming
DELEGATION_ITEMS = ("orq:advisor", "orq:sidekick")  # the output items the platform adds when a tool ran server-side
orq = make_orq()


def run_agent(
    agent: str,
    text: str,
    *,
    store: OrderStore | None = None,
    max_steps: int = 8,
    **kwargs: Any,
) -> dict[str, Any]:
    """Module 08's loop, plus `items`: every output item of the chain, so step 3 can read the delegation."""
    store = store or OrderStore()
    response = orq.responses.create(model=f"agent/{agent}", input=text, **kwargs).model_dump(by_alias=True)
    traces = [response["telemetry"]["trace_id"]]
    tool_calls: list[str] = []
    items = list(response["output"])
    for _ in range(max_steps):
        done_by_server = {o.get("call_id") for o in response["output"] if o["type"].startswith("orq:")}
        pending = [
            o
            for o in response["output"]
            if o["type"] == "function_call" and o["call_id"] not in done_by_server
        ]
        if not pending:
            break
        outputs = []
        for call in pending:
            result = dispatch(store, call["name"], json.loads(call["arguments"] or "{}"))
            tool_calls.append(call["name"])
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(result),
                }
            )
        response = orq.responses.create(
            model=f"agent/{agent}",
            previous_response_id=response["id"],
            input=outputs,
            **kwargs,
        ).model_dump(by_alias=True)
        traces.append(response["telemetry"]["trace_id"])
        items += response["output"]
    answer = " ".join(
        part["text"]
        for item in response["output"]
        if item["type"] == "message"
        for part in item["content"]
        if part["type"] == "output_text"
    )
    return {"text": answer, "tool_calls": tool_calls, "traces": traces, "items": items}


def step_1_inspect() -> None:
    """Read the agent's model and the two delegation tools with the model each one uses."""
    delegating = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)

    print("── Step 1 · Inspect the delegating agent ──────────────")
    print(f"agent    : {delegating['key']} v{delegating['version']} model={delegating['model']['id']}")
    for tool in delegating["settings"]["tools"]:
        if tool["action_type"] in ("advisor", "sidekick"):
            print(f"{tool['action_type']:<8} : configuration={tool.get('configuration')}")
    print("next     : Agents > ws-refund-agent-delegating > Tools in the Studio: the two delegation tools next to the three function tools")


def step_2_run() -> dict[str, Any]:
    """One turn the agent has to refuse; the output items show which tools it delegated to."""
    turn = run_agent(AGENT, QUESTION)
    delegated = [item["type"][4:] for item in turn["items"] if item["type"] in DELEGATION_ITEMS]

    print("── Step 2 · Run a refund the agent has to refuse ──────")
    print(f"question : {QUESTION}")
    print(f"tools    : {' → '.join(turn['tool_calls'])}")
    print(f"delegate : {', '.join(delegated)}")
    print(f"steps    : {len(turn['traces'])} responses")
    print(f"answer   : {turn['text'][:100]}…")
    print(f"trace    : {turn['traces'][-1]}")
    print(f"next     : orq traces thread {turn['traces'][-1]}")
    return turn


def step_3_read_delegation(turn: dict[str, Any]) -> None:
    """For each delegation, what the agent sent and what came back."""
    # Both tools show up twice in `items`: a function_call with the arguments the agent wrote
    # (the advisor's `question`, the sidekick's `task`), then an orq:advisor / orq:sidekick item
    # with the `result`. Match them on call_id.
    exchanges: list[tuple[str, str, str]] = []  # TODO: (item type, what was sent, what came back) for every orq:advisor / orq:sidekick item

    print("── Step 3 · Read what each tool sent and got back ─────")
    if not exchanges:
        print("TODO     : fill in `exchanges` from the function_call arguments and the orq:* results, then rerun")
    for kind, sent, got in exchanges:
        print(f"tool     : {kind}")
        print(f"sent     : {sent[:100]!r}")
        print(f"got      : {got[:100]!r}")
    print("next     : the advisor got the transcript too; the sidekick got only the task")


def step_4_cost_split(turn: dict[str, Any]) -> None:
    """Sum the cost per owner: the agent's own model calls versus each delegation tool."""
    # orq.traces.list_spans(trace_id=...) for each trace in turn["traces"]. A span with a cost whose
    # parent is a span.tool named advisor or sidekick belongs to that tool, the rest to the agent.
    # Skip the root span (type "trace"): it repeats the agent's own model cost.
    rows: list[tuple[str, str, float]] = []  # TODO: (owner, model, cost) per span that carried a cost; sleep ~5 s first, nested spans land late

    print("── Step 4 · Read the cost split in the trace ──────────")
    if not rows:
        print("TODO     : fill in `rows` from the spans of each trace, then rerun")
    total = sum(cost for _, _, cost in rows) or 1
    for owner in ("agent", "advisor", "sidekick"):
        part = [row for row in rows if row[0] == owner]
        if part:
            subtotal = sum(cost for _, _, cost in part)
            print(f"    {owner:<9} {part[0][1]:<14} calls={len(part)}  ${subtotal:.5f}  {100 * subtotal / total:5.1f}%")
    print(f"next     : orq traces get-span {turn['traces'][-1]} <span_id> for any row above, or open the trace in the Studio")


def step_5_broken_advisor() -> None:
    """A copy of the agent whose advisor points at a model that does not exist; the turn still answers."""
    # from app.refund_agent.entities import ensure_delegating_agent
    # ensure_delegating_agent(name="refund-agent-delegating-broken", advisor_model="openai/gpt-does-not-exist")
    # then run_agent(settings.key("refund-agent-delegating-broken"), QUESTION)
    broken_turn: dict[str, Any] | None = None  # TODO: the turn of the broken agent (create it first, see above)

    print("── Step 5 · When the secondary model fails ────────────")
    if broken_turn is None:
        print("TODO     : create the broken agent, run it into `broken_turn`, then rerun")
    else:
        advisor_item = next((item for item in broken_turn["items"] if item["type"] == "orq:advisor"), None)
        print(f"tools    : {' → '.join(broken_turn['tool_calls'])}")
        print(f"answered : {'yes' if broken_turn['text'] else 'no'}")
        print(f"advisor  : {str(advisor_item.get('result') if advisor_item else None)[:100]!r}")
    print("next     : the advisor span in the trace stays ok with no chat span underneath; the failure is in the orq:advisor item")


if __name__ == "__main__":
    step_1_inspect()
    turn = step_2_run()
    step_3_read_delegation(turn)
    step_4_cost_split(turn)
    step_5_broken_advisor()
