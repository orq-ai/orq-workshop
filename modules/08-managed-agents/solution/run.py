# %% [markdown]
# # 08 · Managed agents
#
# The refund agent as a managed orq Agent. Modules 01 to 07 kept the loop in
# `app/refund_agent/agent.py`; here instructions, model, tools, limits, knowledge base and memory
# become one versioned entity, and the app shrinks to "execute this tool call and send the result
# back". Five steps: inspect the agent, invoke it through the Responses API and run its
# `function_call` items locally, stream a reply, give it memory per customer, publish a version and
# pin it with `@version`.
#
# | | |
# |---|---|
# | **Time** | 40 min |
# | **Prerequisites** | modules 00 to 02, `make seed` |
# | **You will have** | the refund agent invoked through the Responses API with a local tool loop, streamed, given memory, versioned and pinned by `@version` |
#
# This file is both the solution script (`make m08`) and the notebook source
# (`make notebooks` turns it into `modules/08-managed-agents/notebook.ipynb`). Run the cells top to
# bottom.

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
TRACES_URL = f"{settings.base_url}/traces"

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
agent_info = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
agent_settings = agent_info["settings"]
tools_as_read = [(tool["action_type"], tool.get("key", tool["display_name"]), tool["id"][-6:]) for tool in agent_settings["tools"]]

print("── Step 1 · Inspect the agent ─────────────────────────")
print(f"agent    : {agent_info['key']} v{agent_info['version']} ({agent_info['status']})")
print(f"model    : {agent_info['model']['id']}")
print(f"limits   : max_iterations {agent_settings['max_iterations']}, max_execution_time {agent_settings['max_execution_time']}s")
print(f"approval : tool_approval_required={agent_settings['tool_approval_required']}")
print(f"tools    : {tools_as_read}  (action_type, key, id suffix: the READ shape)")
print(f"kb       : {agent_info['knowledge_bases']}")
print(f"memory   : {agent_info['memory_stores']}")

# Proof that the read shape is not the write shape: send the GET settings straight back.
try:
    orq.agents.update(agent_key=AGENT, settings=agent_settings)
except Exception as exc:  # noqa: BLE001
    print(f"patch    : rejected, {type(exc).__name__}: {str(exc)[:70]}…")
print("write    : settings.tools = [{'type': 'function', 'key': 'ws-lookup-order'}, ...]")
print("next     : open Agents > ws-refund-agent in the Studio; the Versions tab is used in step 5")

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
    response = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    traces = [response["telemetry"]["trace_id"]]  # every Responses call is its own trace
    called = []
    for _ in range(max_steps):
        # a server-side tool's function_call is followed by an orq:<tool> item with the same call_id
        done_by_server = {item.get("call_id") for item in response["output"] if item["type"].startswith("orq:")}
        calls = [item for item in response["output"] if item["type"] == "function_call" and item["call_id"] not in done_by_server]
        if not calls:
            break
        outputs = []
        for call in calls:
            result = dispatch(store, call["name"], json.loads(call["arguments"] or "{}"))
            called.append(call["name"])
            outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)})
        # state is server-side: send only the tool results, chained on the previous response id
        response = orq.responses.create(model=f"agent/{agent}", previous_response_id=response["id"], input=outputs, **kw).model_dump(by_alias=True)
        traces.append(response["telemetry"]["trace_id"])
    text_out = " ".join(
        content["text"]
        for item in response["output"]
        if item["type"] == "message"
        for content in item["content"]
        if content["type"] == "output_text"
    )
    return {"text": text_out, "tool_calls": called, "traces": traces, "response_id": response["id"], "model": response["model"], "usage": response["usage"]}


# %%
started = time.time()
out = run_agent(AGENT, QUESTION)
elapsed = time.time() - started

print("── Step 2 · Invoke it and execute the tool calls ──────")
print(f"question : {QUESTION}")
print(f"tools    : {' → '.join(out['tool_calls'])}")
print(f"requests : {len(out['traces'])} in {elapsed:.1f}s, cost ${out['usage']['total_cost']:.5f}")
print(f"answer   : {out['text'][:100]}…")
print(f"first    : {out['traces'][0]}")
print(f"last     : {out['traces'][-1]}")
print(f"next     : run `orq traces thread {out['traces'][-1]}`; the last trace renders the whole conversation")

# %% [markdown]
# One request per round of the loop, one trace per request. The last one renders the whole
# conversation because state is server-side. The model sometimes confirms the order first and waits
# ("Would you like to proceed?"): that is the instructions working, not a bug.
#
# ## Step 3 · Stream
#
# `stream=True` returns an event stream. Text arrives as `response.output_text.delta` events; a
# `function_call` arrives as `response.function_call_arguments.delta` and `.done`. A prompt the agent
# answers with a tool call streams no text at all, so the example asks something it can answer alone.

# %%
started = time.time()
first_token_seconds = None
tokens = []
event_count = 0
# no tool needed: a question the agent answers with get_policy streams only function_call_arguments.delta events
with orq.responses.create(model=f"agent/{AGENT}", input="Say hello in one sentence and ask how you can help.", stream=True) as events:
    for event in events:
        event_count += 1
        data = event.model_dump(by_alias=True).get("data", {})
        if data.get("type") == "response.output_text.delta":
            first_token_seconds = first_token_seconds or time.time() - started
            tokens.append(data["delta"])

print("── Step 3 · Stream ────────────────────────────────────")
print(f"events   : {event_count}")
print(f"first    : token at {first_token_seconds:.2f}s")
print(f"tokens   : {tokens[:6]}")
print(f"text     : {''.join(tokens)}")
print("next     : the first token arrived well before the full text; that is what a chat UI renders")

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
    """Create the memory store and the memory copy of the agent if missing. Safe to rerun."""
    from app.refund_agent.entities import agent_payload

    if not any(store.key == MEMORY_STORE for store in orq.memory_stores.list(limit=100).data or []):
        orq.memory_stores.create(
            key=MEMORY_STORE,
            embedding_config={"model": settings.embedding_model},
            description="Workshop: per-customer facts the refund agent should remember (name, preferences).",
            path=settings.path,
        )
        print(f"created  : memory store {MEMORY_STORE}")
    try:
        orq.agents.retrieve(agent_key=MEMORY_AGENT)
        return MEMORY_AGENT
    except Exception:  # noqa: BLE001  (not found: create it below)
        pass
    kb = next(knowledge.id for knowledge in orq.knowledge.list(limit=100).data if knowledge.key == settings.key("refund-policy"))
    payload = agent_payload("fixed", knowledge_base_id=kb, tool_keys=[settings.key("lookup-order"), settings.key("issue-refund"), settings.key("get-policy")])
    payload["key"] = MEMORY_AGENT
    payload["display_name"] = "Refund agent (memory)"
    payload["instructions"] += (
        "\n\nMemory: at the start of every conversation call retrieve_memory_stores, then query_memory_store with the query "
        "'customer name and preferences'. When the customer states their name or a preference, call write_memory_store once with a "
        "single sentence that contains the customer's full name and every stated preference, for example "
        "'Customer name: Jane Okafor. Prefers store credit over card refunds.' Greet returning customers by name when memory has it."
    )
    payload["settings"]["tools"] += [{"type": "retrieve_memory_stores"}, {"type": "query_memory_store"}, {"type": "write_memory_store"}]
    payload["memory_stores"] = [MEMORY_STORE]
    orq.agents.create(**payload)
    print(f"created  : agent {MEMORY_AGENT}")
    return MEMORY_AGENT


# %%
print("── Step 4 · Memory ────────────────────────────────────")
agent = ensure_memory_agent()
entity = {"entity_id": f"{settings.identity_id}-{int(time.time())}"}   # fresh entity per run, so recall is not stale
first_turn = run_agent(agent, "Hi, my name is Jane Okafor. Please remember that I prefer store credit over card refunds.", memory=entity)
second_turn = run_agent(agent, "Quick check: do you remember my name and how I like my refunds?", memory=entity)

print(f"agent    : {agent}")
print(f"entity   : {entity['entity_id']}")
print(f"turn 1   : {first_turn['text'][:100]}")
print(f"turn 2   : {second_turn['text'][:100]}")
print(f"trace 2  : {second_turn['traces'][-1]}")
print(f"next     : open trace 2; expect retrieve_memory_stores and query_memory_store spans, then `orq memory-stores list-memories {MEMORY_STORE}`")

# %% [markdown]
# ## Step 5 · Versions and `@version` routing
#
# `orq.agents.update(..., version_increment="minor", version_description=...)` publishes a
# version. Invoke a pinned version with `agent/<key>@<version>`, an environment with
# `agent/<key>@<environment>`; no suffix means `latest`. `@production` resolves once you assign the
# environment in the Studio (**Agents** > `ws-refund-agent` > **Versions**). The bump only changes
# the description and is skipped on re-runs.

# %%
agent_info = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
marker = "[m08 v-bump]"  # the marker in the description makes the bump idempotent

print("── Step 5 · Versions and @version routing ─────────────")
if marker not in (agent_info["description"] or ""):
    agent_info = orq.agents.update(
        agent_key=AGENT,
        description=f"{agent_info['description']} {marker}",
        version_increment="minor",
        version_description="Module 08: minor bump to demo @version routing",
    ).model_dump(by_alias=True)
    print(f"version  : bumped {AGENT} to v{agent_info['version']}")
else:
    print(f"version  : {AGENT} already at v{agent_info['version']} (bump skipped, idempotent)")

for suffix in ("@1.0.0", f"@{agent_info['version']}", "@latest", "@production"):
    model_ref = f"agent/{AGENT}{suffix}"
    try:
        response = orq.responses.create(model=model_ref, input="One sentence: what is the refund window?").model_dump(by_alias=True)
        print(f"call     : {model_ref:<34} ok, trace {response['telemetry']['trace_id']}")
    except Exception as exc:  # noqa: BLE001
        message = str(exc).split('"message":"')[-1].split('"')[0]  # the API error message, without the SDK wrapper
        print(f"call     : {model_ref:<34} {message[:60]}")
print("next     : assign the production environment in Agents > ws-refund-agent > Versions, rerun, and @production resolves")

# %% [markdown]
# ## Step 6 · The same from the CLI
#
# ```bash
# orq responses create --model agent/ws-refund-agent --input '"One sentence: what is the refund window?"' -o json | jq '{trace: .telemetry.trace_id, text: .output[0].content[0].text}'
# orq traces search --from 5m --to now -o json | jq '.data[] | select(.name == "ws-refund-agent") | .trace_id' | head -3
# ```

# %%
print("── Step 6 · The same from the CLI ─────────────────────")
print("search   : orq traces search --from 5m --to now")
print(f"next     : open {TRACES_URL} and search a trace id from the steps above")

# %% [markdown]
# ## What to take away
#
# - A managed agent never runs your Python: `function_call` items come back to you, and you answer
#   with `function_call_output` plus `previous_response_id`. Match on `call_id`.
# - Calls followed by an `orq:<tool>` item were already answered server-side; do not answer them.
# - Every Responses call is its own trace; the last one renders the whole conversation.
# - Memory tools make `memory.entity_id` mandatory on every call, so put memory on a copy.
# - `agent/<key>@<version>` pins a version; `@<environment>` follows whatever the Studio assigns.
