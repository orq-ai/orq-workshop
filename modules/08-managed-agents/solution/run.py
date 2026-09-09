"""Module 08 solution: the refund agent as a managed orq Agent.

Factor 4: tools are structured outputs. The agent emits `function_call` items; this file executes them.
Factor 6: launch / pause / resume. Every turn is a Responses API call, state lives server-side.
Factor 10: small, focused agents. One agent, three tools, eight iterations max.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.tools import OrderStore, dispatch

AGENT = settings.key("refund-agent")                      # ws-refund-agent
MEMORY_AGENT = settings.key("refund-agent-memory")        # ws-refund-agent-memory (a copy, see step 4)
MEMORY_STORE = settings.key("refund-memory").replace("-", "_")  # ws_refund_memory: memory keys reject "-"
QUESTION = "Refund ord_a2 please, the dock does not fit."

orq = make_orq()


# ---------------------------------------------------------------- step 1: inspect

def step_1_inspect() -> None:
    a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
    s = a["settings"]
    print(f"[1] {a['key']} v{a['version']} model={a['model']['id']} status={a['status']}")
    print(f"    max_iterations={s['max_iterations']} max_execution_time={s['max_execution_time']}s tool_approval_required={s['tool_approval_required']}")
    print(f"    tools (as READ): {[(t['action_type'], t['key'], t['id'][-6:]) for t in s['tools']]}")
    print(f"    knowledge_bases={a['knowledge_bases']} memory_stores={a['memory_stores']}")
    # Reads and writes have different shapes. A GET body PATCHed back is rejected by the SDK.
    try:
        orq.agents.update(agent_key=AGENT, settings=s)
    except Exception as exc:  # noqa: BLE001
        print(f"    PATCH of the GET body -> {type(exc).__name__}: {str(exc)[:70]}...")
    print("    write shape: settings.tools = [{'type': 'function', 'key': 'ws-lookup-order'}, ...]")


# ---------------------------------------------------------------- step 2: invoke + tool loop

def run_agent(agent: str, text: str, *, store: OrderStore | None = None, max_steps: int = 8, **kw: Any) -> dict[str, Any]:
    """One customer turn. Executes every `function_call` locally and continues with previous_response_id."""
    store = store or OrderStore()
    r = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    traces, called = [r["telemetry"]["trace_id"]], []
    for _ in range(max_steps):
        # Server-side tools (memory, advisor, current_date...) also emit a function_call item, followed by an
        # `orq:<tool>` item with the result. Only calls without a server result are ours to execute.
        done_by_server = {o.get("call_id") for o in r["output"] if o["type"].startswith("orq:")}
        calls = [o for o in r["output"] if o["type"] == "function_call" and o["call_id"] not in done_by_server]
        if not calls:
            break
        outputs = []
        for c in calls:
            result = dispatch(store, c["name"], json.loads(c["arguments"] or "{}"))
            called.append(c["name"])
            outputs.append({"type": "function_call_output", "call_id": c["call_id"], "output": json.dumps(result)})
        r = orq.responses.create(model=f"agent/{agent}", previous_response_id=r["id"], input=outputs, **kw).model_dump(by_alias=True)
        traces.append(r["telemetry"]["trace_id"])
    text_out = " ".join(c["text"] for o in r["output"] if o["type"] == "message" for c in o["content"] if c["type"] == "output_text")
    return {"text": text_out, "tool_calls": called, "traces": traces, "response_id": r["id"], "model": r["model"], "usage": r["usage"]}


def step_2_invoke() -> None:
    t0 = time.time()
    out = run_agent(AGENT, QUESTION)
    print(f"[2] tools={out['tool_calls']} steps={len(out['traces'])} {time.time() - t0:.1f}s cost=${out['usage']['total_cost']:.5f}")
    print(f"    answer: {out['text'][:110]}")
    print(f"    first trace: {out['traces'][0]}   last trace: {out['traces'][-1]}")
    print(f"    $ orq traces thread {out['traces'][-1]}")


# ---------------------------------------------------------------- step 3: streaming

def step_3_stream() -> None:
    t0 = time.time()
    first, tokens, n = None, [], 0
    with orq.responses.create(model=f"agent/{AGENT}", input="In one sentence, what is the refund window?", stream=True) as events:
        for ev in events:
            n += 1
            d = ev.model_dump(by_alias=True).get("data", {})
            if d.get("type") == "response.output_text.delta":
                first = first or time.time() - t0
                tokens.append(d["delta"])
    print(f"[3] stream: {n} events, first token at {first:.2f}s, first tokens={tokens[:6]}")
    print(f"    text: {''.join(tokens)}")


# ---------------------------------------------------------------- step 4: memory

def ensure_memory_agent() -> str:
    """A copy of the refund agent with a memory store and the memory tools.

    Not attached to ws-refund-agent itself: an agent with memory tools returns 400 unless every call
    carries memory.entity_id, which would break the other modules that invoke agent/ws-refund-agent.
    """
    from app.refund_agent.entities import agent_payload

    if not any(m.key == MEMORY_STORE for m in orq.memory_stores.list(limit=100).data or []):
        orq.memory_stores.create(key=MEMORY_STORE, embedding_config={"model": settings.embedding_model},
                                 description="Workshop: per-customer facts the refund agent should remember (name, preferences).", path=settings.path)
        print(f"    created memory store {MEMORY_STORE}")
    try:
        orq.agents.retrieve(agent_key=MEMORY_AGENT)
        return MEMORY_AGENT
    except Exception:  # noqa: BLE001
        pass
    kb = next(k.id for k in orq.knowledge.list(limit=100).data if k.key == settings.key("refund-policy"))
    p = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[settings.key("lookup-order"), settings.key("issue-refund"), settings.key("get-policy")])
    p["key"], p["display_name"] = MEMORY_AGENT, "Refund agent (memory)"
    p["instructions"] += (
        "\n\nMemory: at the start of every conversation call retrieve_memory_stores, then query_memory_store with the query "
        "'customer name and preferences'. When the customer states their name or a preference, call write_memory_store once with a "
        "single sentence that contains the customer's full name and every stated preference, for example "
        "'Customer name: Jane Okafor. Prefers store credit over card refunds.' Greet returning customers by name when memory has it."
    )
    p["settings"]["tools"] += [{"type": "retrieve_memory_stores"}, {"type": "query_memory_store"}, {"type": "write_memory_store"}]
    p["memory_stores"] = [MEMORY_STORE]
    orq.agents.create(**p)
    print(f"    created agent {MEMORY_AGENT}")
    return MEMORY_AGENT


def step_4_memory() -> None:
    agent = ensure_memory_agent()
    entity = {"entity_id": f"{settings.identity_id}-{int(time.time())}"}   # fresh entity per run, so recall is not stale
    a = run_agent(agent, "Hi, my name is Jane Okafor. Please remember that I prefer store credit over card refunds.", memory=entity)
    b = run_agent(agent, "Quick check: do you remember my name and how I like my refunds?", memory=entity)
    print(f"[4] memory entity={entity['entity_id']}")
    print(f"    turn 1: {a['text'][:100]}")
    print(f"    turn 2: {b['text'][:100]}")
    print(f"    trace 2: {b['traces'][-1]}  (spans: retrieve_memory_stores, query_memory_store)")


# ---------------------------------------------------------------- step 5: versions

def step_5_versions() -> None:
    a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
    marker = "[m08 v-bump]"
    if marker not in (a["description"] or ""):
        a = orq.agents.update(agent_key=AGENT, description=f"{a['description']} {marker}", version_increment="minor",
                              version_description="Module 08: minor bump to demo @version routing").model_dump(by_alias=True)
        print(f"[5] bumped {AGENT} -> v{a['version']}")
    else:
        print(f"[5] {AGENT} already at v{a['version']} (bump skipped, idempotent)")
    for suffix in ("@1.0.0", f"@{a['version']}", "@latest", "@production"):
        try:
            r = orq.responses.create(model=f"agent/{AGENT}{suffix}", input="One sentence: what is the refund window?").model_dump(by_alias=True)
            print(f"    agent/{AGENT}{suffix:<12} ok   trace={r['telemetry']['trace_id']}")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).split('"message":"')[-1].split('"')[0]
            print(f"    agent/{AGENT}{suffix:<12} {msg[:60]}")


if __name__ == "__main__":
    step_1_inspect()
    step_2_invoke()
    step_3_stream()
    step_4_memory()
    step_5_versions()
    print(f"open {settings.base_url}/traces and search a trace id, or run: orq traces search --from 5m --to now")
