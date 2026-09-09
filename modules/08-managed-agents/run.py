"""Module 08 starter: the refund agent as a managed orq Agent.

The agent ws-refund-agent already exists (make seed). Your job is the client side: invoke it through the
Responses API, execute the function_call items it returns, continue with previous_response_id.
"""

from __future__ import annotations

import json
from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent")   # ws-refund-agent
QUESTION = "Refund ord_a2 please, the dock does not fit."
orq = make_orq()


def step_1_inspect() -> None:
    a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
    s = a["settings"]
    print(f"[1] {a['key']} v{a['version']} model={a['model']['id']} max_iterations={s['max_iterations']}")
    print(f"    tools (as READ): {[(t['action_type'], t['key']) for t in s['tools']]}")
    # Writes use a different shape: [{"type": "function", "key": "ws-lookup-order"}, ...]. Never PATCH the GET body back.


def run_agent(agent: str, text: str, *, store: OrderStore | None = None, max_steps: int = 8, **kw: Any) -> dict[str, Any]:
    """One customer turn: execute every function_call locally, continue until the agent answers with a message."""
    store = store or OrderStore()
    r = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    traces, called = [r["telemetry"]["trace_id"]], []
    for _ in range(max_steps):
        calls = [o for o in r["output"] if o["type"] == "function_call"]
        if not calls:
            break
        outputs = []
        for c in calls:
            result = dispatch(store, c["name"], json.loads(c["arguments"] or "{}"))
            called.append(c["name"])
            # TODO: build the function_call_output input item (keyed on call_id, output as a JSON string)
            outputs.append({})
        # TODO: continue the same response chain with previous_response_id=r["id"] and input=outputs
        r = r
        traces.append(r["telemetry"]["trace_id"])
        break
    text_out = " ".join(c["text"] for o in r["output"] if o["type"] == "message" for c in o["content"] if c["type"] == "output_text")
    return {"text": text_out, "tool_calls": called, "traces": traces}


def step_2_invoke() -> None:
    out = run_agent(AGENT, QUESTION)
    print(f"[2] tools={out['tool_calls']} steps={len(out['traces'])} answer={out['text'][:80]!r}")
    print(f"    $ orq traces thread {out['traces'][-1]}")


def step_3_stream() -> None:
    # TODO: the same call with stream=True; print the first response.output_text.delta events
    print("[3] stream: TODO")


def step_4_memory() -> None:
    # TODO: memory store ws_refund_memory + a copy of the agent with memory tools; two calls with memory={"entity_id": ...}
    print("[4] memory: TODO")


def step_5_versions() -> None:
    # TODO: orq.agents.update(agent_key=AGENT, ..., version_increment="minor", version_description="...")
    #       then invoke agent/ws-refund-agent@1.0.0, @1.1.0, @latest, @production
    print("[5] versions: TODO")


if __name__ == "__main__":
    step_1_inspect()
    step_2_invoke()
    step_3_stream()
    step_4_memory()
    step_5_versions()
