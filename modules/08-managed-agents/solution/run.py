# %% [markdown]
# # 08 · Managed agents
#
# The refund agent as a managed orq Agent. Modules 01 to 07 kept the loop in `app/refund_agent/agent.py`; here instructions, model, tools, limits, knowledge base and memory become one versioned entity, and the app shrinks to "execute this tool call and send the result back". Five steps: inspect the agent, invoke it through the Responses API and run its `function_call` items locally, stream a reply, give it memory per customer, publish a version and pin it with `@version`.
#
# | | |
# |---|---|
# | **Time** | 40 min |
# | **Prerequisites** | modules 00 to 02, `make seed` |
# | **You will have** | the refund agent invoked through the Responses API with a local tool loop, streamed, given memory, versioned and pinned by `@version` |
#
# This file is both the solution script (`make m08`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
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

# %% [markdown]
# ## Step 1 · Inspect the agent
#
# `make seed` created `ws-refund-agent` with the three function tools. Reads and writes have
# different shapes: a GET returns tools as `{action_type, id, key, requires_approval}`; a create or
# update wants `{"type": "function", "key": "ws-lookup-order"}`. PATCHing a GET body back is
# rejected by the SDK. Inline function schemas are rejected too: register the tool once
# (`orq tools create`), then reference it by key.

# %%
a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
s = a["settings"]
print(f"[1] {a['key']} v{a['version']} model={a['model']['id']} status={a['status']}")
print(f"    max_iterations={s['max_iterations']} max_execution_time={s['max_execution_time']}s tool_approval_required={s['tool_approval_required']}")
print(f"    tools (as READ): {[(t['action_type'], t.get('key', t['display_name']), t['id'][-6:]) for t in s['tools']]}")
print(f"    knowledge_bases={a['knowledge_bases']} memory_stores={a['memory_stores']}")
try:
    orq.agents.update(agent_key=AGENT, settings=s)
except Exception as exc:  # noqa: BLE001
    print(f"    PATCH of the GET body -> {type(exc).__name__}: {str(exc)[:70]}...")
print("    write shape: settings.tools = [{'type': 'function', 'key': 'ws-lookup-order'}, ...]")

# %% [markdown]
# ## Step 2 · Invoke it and execute the tool calls
#
# `orq.responses.create(model="agent/<key>", input=...)` returns output items. A `function_call`
# item is ours to execute; we answer with a `function_call_output` item and
# `previous_response_id`, and the agent continues. Server-side tools (memory, advisor,
# `current_date`) also emit a `function_call`, followed by an `orq:<tool>` item with the result:
# only calls without a server result are ours.
#
# **Try it first:** write the loop before reading `run_agent`.

# %%
def run_agent(agent: str, text: str, *, store: OrderStore | None = None, max_steps: int = 8, **kw: Any) -> dict[str, Any]:
    """One customer turn. Executes every `function_call` locally and continues with previous_response_id."""
    store = store or OrderStore()
    r = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    traces, called = [r["telemetry"]["trace_id"]], []
    for _ in range(max_steps):
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


t0 = time.time()
out = run_agent(AGENT, QUESTION)
print(f"[2] tools={out['tool_calls']} steps={len(out['traces'])} {time.time() - t0:.1f}s cost=${out['usage']['total_cost']:.5f}")
print(f"    answer: {out['text'][:110]}")
print(f"    first trace: {out['traces'][0]}   last trace: {out['traces'][-1]}")
print(f"    $ orq traces thread {out['traces'][-1]}")

# %% [markdown]
# Four requests, four traces: each Responses call is its own trace. The last one renders the whole
# conversation because state is server-side. The model sometimes confirms the order first and waits
# ("Would you like to proceed?"): that is the instructions working, not a bug.
#
# ## Step 3 · Stream
#
# `stream=True` returns an event stream. Text arrives as `response.output_text.delta` events; a
# `function_call` arrives as `response.function_call_arguments.delta` and `.done`. A prompt the agent
# answers with a tool call streams no text at all, so the example asks something it can answer alone.

# %%
t0 = time.time()
first, tokens, n = None, [], 0
with orq.responses.create(model=f"agent/{AGENT}", input="Say hello in one sentence and ask how you can help.", stream=True) as events:   # no tool needed: a question the agent answers with get_policy streams only function_call_arguments.delta events
    for ev in events:
        n += 1
        d = ev.model_dump(by_alias=True).get("data", {})
        if d.get("type") == "response.output_text.delta":
            first = first or time.time() - t0
            tokens.append(d["delta"])
print(f"[3] stream: {n} events, first token at {first:.2f}s, first tokens={tokens[:6]}")
print(f"    text: {''.join(tokens)}")

# %% [markdown]
# ## Step 4 · Memory
#
# A memory store is an embedding-backed store of documents per `entity_id`. The agent reads and
# writes it through server-side tools, so it needs three things: the store attached, the tools
# `retrieve_memory_stores`, `query_memory_store`, `write_memory_store` in `settings.tools`, and
# instructions that say when to save and when to query. Each call then carries
# `memory={"entity_id": ...}`.
#
# Two deliberate choices: the store key is `ws_refund_memory` (memory keys reject `-`), and the
# memory goes on a copy, `ws-refund-agent-memory`. Once an agent has memory tools, every call
# without `memory.entity_id` is a 400, which would break every other module that invokes
# `agent/ws-refund-agent`.

# %%
def ensure_memory_agent() -> str:
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


agent = ensure_memory_agent()
entity = {"entity_id": f"{settings.identity_id}-{int(time.time())}"}   # fresh entity per run, so recall is not stale
a = run_agent(agent, "Hi, my name is Jane Okafor. Please remember that I prefer store credit over card refunds.", memory=entity)
b = run_agent(agent, "Quick check: do you remember my name and how I like my refunds?", memory=entity)
print(f"[4] memory entity={entity['entity_id']}")
print(f"    turn 1: {a['text'][:100]}")
print(f"    turn 2: {b['text'][:100]}")
print(f"    trace 2: {b['traces'][-1]}  (spans: retrieve_memory_stores, query_memory_store)")

# %% [markdown]
# Check the store: `orq memory-stores list-memories ws_refund_memory`.
#
# ## Step 5 · Versions and `@version` routing
#
# `orq.agents.update(..., version_increment="minor", version_description=...)` publishes a
# version. Invoke a pinned version with `agent/<key>@<version>`, an environment with
# `agent/<key>@<environment>`; no suffix means `latest`. `@production` resolves once you assign the
# environment in the Studio (**Agents** > `ws-refund-agent` > **Versions**). The bump only changes
# the description and is skipped on re-runs.

# %%
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

# %% [markdown]
# ## Step 6 · The same from the CLI
#
# ```bash
# orq responses create --model agent/ws-refund-agent --input '"One sentence: what is the refund window?"' -o json | jq '{trace: .telemetry.trace_id, text: .output[0].content[0].text}'
# orq traces search --from 5m --to now -o json | jq '.data[] | select(.name == "ws-refund-agent") | .trace_id' | head -3
# ```

# %%
print(f"open {settings.base_url}/traces and search a trace id, or run: orq traces search --from 5m --to now")
