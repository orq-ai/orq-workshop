# %% [markdown]
# # 15 · Advisor and sidekick
#
# One agent, one model, every step. Size the model for the hardest step and every step gets expensive;
# size it for the routine steps and it fails where quality matters. The `advisor` and `sidekick` tools
# break that trade-off: the agent stays on a cheap model and hands single steps to a second model
# configured at design time. Five steps: inspect the delegating agent, run a hard refund, read what
# each tool sent and got back, read the cost split in the trace, and watch the agent survive a broken
# secondary model.
#
# | | |
# |---|---|
# | **Time** | 30 min |
# | **Prerequisites** | module 08, `make seed` |
# | **You will have** | a refund agent that consults `gpt-5.6-sol` only before a refusal and delegates the closing note to `gpt-5.4-nano`, with the cost of each choice read off one trace |
#
# This file is both the solution script (`make m15`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
from __future__ import annotations

import json
import time
from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import ensure_delegating_agent
from app.refund_agent.tools import OrderStore, dispatch

AGENT = ensure_delegating_agent()  # ws-refund-agent-delegating
BASE = settings.key("refund-agent")  # ws-refund-agent, for comparison
BROKEN = settings.key("refund-agent-delegating-broken")  # step 5
QUESTION = "Refund ord_a6 please, the frame arrived scratched."  # EUR 620: above the limit, so a refusal is coming
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
    """One customer turn through module 08's loop; keeps every output item so step 3 can read the delegation.

    Execute the `function_call` items that are ours, skip the ones with an `orq:*` sibling (the
    platform already ran those), continue with `previous_response_id` until no call is pending.
    """
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
    return {
        "text": answer,
        "tool_calls": tool_calls,
        "traces": traces,
        "items": items,
        "usage": response["usage"],
    }


# %% [markdown]
# ## Step 1 · Inspect the delegating agent
#
# `make seed` created `ws-refund-agent-delegating`: the fixed refund agent plus two entries in
# `settings.tools`. Neither is a sub-agent. The second model gets one call, no tools, no memory.
#
# | | Advisor | Sidekick |
# |---|---|---|
# | Sends | the transcript plus a question | a task, nothing else |
# | Returns | advice | a finished artifact |
# | Who decides | the agent | the sidekick |
# | Config | `model`, `max_uses`, `max_transcript_tokens`, `max_tokens` | `model`, `max_uses`, `max_tokens`, `system_prompt`, `output_format` |
#
# The instructions matter more than the configuration: a tool the instructions never name is
# rarely called. Ours say *before refusing, ask the advisor* and *after any decision, let the
# sidekick write the closing note*.

# %%
delegating = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
base = orq.agents.retrieve(agent_key=BASE).model_dump(by_alias=True)

print("── Step 1 · Inspect the delegating agent ──────────────")
print(f"agent    : {delegating['key']} v{delegating['version']} model={delegating['model']['id']}")
print(f"base     : {base['key']} model={base['model']['id']}")
for tool in delegating["settings"]["tools"]:
    if tool["action_type"] not in ("advisor", "sidekick"):
        continue  # the three function tools, same as the base agent
    config = tool.get("configuration") or {}
    if tool["action_type"] == "advisor":
        extra = f"max_transcript_tokens={config.get('max_transcript_tokens')}"
    else:
        extra = f"output_format={config.get('output_format')!r}"
    print(f"{tool['action_type']:<8} : model={config.get('model')} max_uses={config.get('max_uses')} {extra}")

# %%
rules = [line for line in delegating["instructions"].splitlines() if line.startswith("- ")][-2:]
print(f"rules    : {rules[0][:80]}... / {rules[1][:80]}...")
print("next     : Agents > ws-refund-agent-delegating > Tools in the Studio: the two delegation tools next to the three function tools")

# %% [markdown]
# ## Step 2 · Run a refund the agent has to refuse
#
# `ord_a6` is a EUR 620 frame; the policy caps refunds at EUR 500. The instructions send the agent to
# the advisor before it refuses, and to the sidekick for the closing note. `run_agent` (above) is
# module 08's loop, plus the full list of output items: that is where the delegation shows up.

# %%
started = time.time()
turn = run_agent(AGENT, QUESTION)
elapsed = time.time() - started
delegated = [item["type"][4:] for item in turn["items"] if item["type"] in DELEGATION_ITEMS]

print("── Step 2 · Run a refund the agent has to refuse ──────")
print(f"question : {QUESTION}")
print(f"tools    : {' → '.join(turn['tool_calls'])}")
print(f"delegate : {', '.join(delegated)}")
print(f"steps    : {len(turn['traces'])} responses in {elapsed:.1f}s")
print(f"answer   : {turn['text'][:100]}…")
print(f"trace    : {turn['traces'][-1]}")
print(f"next     : orq traces thread {turn['traces'][-1]}")

# %% [markdown]
# ## Step 3 · Read what each tool sent and got back
#
# Both tools show up twice in the output: a `function_call` item with the arguments the agent wrote,
# then an `orq:advisor` / `orq:sidekick` item with the result. The advisor's arguments are a question
# (the platform adds the transcript); the sidekick's are the task and nothing else. That is the whole
# difference between the two, and the reason a sidekick is the wrong tool for a judgement.

# %%
calls_by_id = {item["call_id"]: item for item in turn["items"] if item["type"] == "function_call"}

print("── Step 3 · Read what each tool sent and got back ─────")
for item in turn["items"]:
    if item["type"] not in DELEGATION_ITEMS:
        continue
    call = calls_by_id.get(item["call_id"])
    arguments = json.loads(call["arguments"] or "{}") if call else {}
    sent = arguments.get("question") or arguments.get("task") or json.dumps(arguments)
    print(f"tool     : {item['type']}")
    print(f"sent     : {sent[:100]!r}")
    print(f"got      : {str(item.get('result'))[:100]!r}")
print("next     : the advisor got the transcript too; the sidekick got only the task line above")

# %% [markdown]
# ## Step 4 · Read the cost split in the trace
#
# Each secondary call goes through the AI Gateway on its own, so it is metered on its own and
# appears as a nested span: `advisor` (span.tool) > `chat gpt-5.6-sol`, `sidekick` > `chat gpt-5.4-nano`.
# Sum the agent's own `chat openai/gpt-5.6-luna` spans and compare. This is the number that says
# whether the escalation was worth it.

# %%
time.sleep(5)  # nested tool spans arrive a few seconds after the response

rows: list[tuple[str, str, float]] = []  # (owner, model, cost) per span that carried a cost
for trace_id in turn["traces"]:
    spans = [s.model_dump(by_alias=True) for s in orq.traces.list_spans(trace_id=trace_id).data or []]
    by_id = {span["span_id"]: span for span in spans}
    for span in spans:
        if span["cost"]["total"] <= 0 or span["type"] == "trace":
            continue  # the root span of type `trace` repeats the agent's own model cost
        parent = by_id.get(span.get("parent_span_id") or "")
        owner = parent["name"] if parent and parent["type"] == "span.tool" else "agent"
        rows.append((owner, span["model"], span["cost"]["total"]))
total = sum(cost for _, _, cost in rows) or 1  # guard the division when spans have not landed yet

print("── Step 4 · Read the cost split in the trace ──────────")
print(f"total    : ${total:.5f} over {len(turn['traces'])} traces")
for owner in ("agent", "advisor", "sidekick"):
    part = [row for row in rows if row[0] == owner]
    if not part:
        continue
    subtotal = sum(cost for _, _, cost in part)
    print(f"    {owner:<9} {part[0][1]:<14} calls={len(part)}  ${subtotal:.5f}  {100 * subtotal / total:5.1f}%")
print(f"next     : orq traces get-span {turn['traces'][-1]} <span_id> for any row above, or open the trace in the Studio")

# %% [markdown]
# ## Step 5 · When the secondary model fails
#
# A copy of the agent points its advisor at a model that does not exist. The turn does not fail:
# the `orq:advisor` item carries the error text, the advisor span stays `ok`, and the agent answers
# from its own model. So a broken advisor degrades quality silently. Alert on the advisor's error
# text, or on `genai.error_rate` filtered to the advisor's model (module 14), not on the agent.

# %%
print("── Step 5 · When the secondary model fails ────────────")
try:
    orq.agents.retrieve(agent_key=BROKEN)
except Exception:  # noqa: BLE001  not there yet: build it once, the same way make seed built the working one
    ensure_delegating_agent(
        name="refund-agent-delegating-broken",
        advisor_model="openai/gpt-does-not-exist",
    )
    print(f"created  : {BROKEN}")

broken_turn = run_agent(BROKEN, QUESTION)
advisor_item = next((item for item in broken_turn["items"] if item["type"] == "orq:advisor"), None)

print(f"agent    : {BROKEN} (advisor on openai/gpt-does-not-exist)")
print(f"tools    : {' → '.join(broken_turn['tool_calls'])}")
print(f"answered : {'yes' if broken_turn['text'] else 'no'}")
print(f"advisor  : {str(advisor_item.get('result') if advisor_item else None)[:100]!r}")

# %%
time.sleep(5)  # same as step 4: give the nested spans time to land
for trace_id in broken_turn["traces"]:
    advisor_spans = [s for s in orq.traces.list_spans(trace_id=trace_id).data or [] if s.name == "advisor"]
    if advisor_spans:
        advisor_cost = sum(span.cost.total for span in advisor_spans)
        print(f"trace    : {trace_id}: {len(advisor_spans)} advisor span(s), status={advisor_spans[0].status} cost=${advisor_cost:.5f}, no chat span underneath")
print("verdict  : the turn did not fail; the failure is in the orq:advisor item, not in the HTTP status")
print("next     : watch for it in the trace, not in genai.error_rate")

# %% [markdown]
# ## Step 6 · The same from the CLI
#
# ```bash
# orq agents retrieve ws-refund-agent-delegating -o json | jq '.settings.tools[] | select(.action_type == "advisor" or .action_type == "sidekick") | {action_type, configuration}'
# orq responses create --model agent/ws-refund-agent-delegating --input '"Refund ord_a6 please, the frame arrived scratched."' -o json | jq '[.output[] | select(.type | startswith("orq:")) | {type, result}]'
# ```
#
# ## What to take away
#
# - Advisor and sidekick are one model call each, no tools, no memory. The advisor sees the
#   transcript and answers a question; the sidekick sees a task and returns an artifact.
# - The decision stays with the agent. Delegation changes which model thinks, not who acts.
# - Every secondary call is its own span with its own cost. One advisor call can cost more than the
#   rest of the turn: read the split before you decide it was worth it.
# - A failing secondary model does not fail the turn. Its error travels as advice in the
#   `orq:advisor` item, so watch the trace, not the HTTP status.

# %%
print(f"open {settings.base_url}/traces and search {turn['traces'][-1]}: the advisor and sidekick spans sit under agent.response with their own cost")
