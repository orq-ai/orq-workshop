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

orq = make_orq()

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
a = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
b = orq.agents.retrieve(agent_key=BASE).model_dump(by_alias=True)
print(
    f"[1] {a['key']} v{a['version']} model={a['model']['id']}   (base {b['key']} model={b['model']['id']})"
)
for t in a["settings"]["tools"]:
    if t["action_type"] in ("advisor", "sidekick"):
        cfg = t.get("configuration") or {}
        print(
            f"    {t['action_type']:<9} model={cfg.get('model')} max_uses={cfg.get('max_uses')} "
            + (
                f"max_transcript_tokens={cfg.get('max_transcript_tokens')}"
                if t["action_type"] == "advisor"
                else f"output_format={cfg.get('output_format')!r}"
            )
        )
extra = [l for l in a["instructions"].splitlines() if l.startswith("- ")][-2:]
print(f"    instructions, last two rules: {extra[0][:80]}... / {extra[1][:80]}...")

# %% [markdown]
# ## Step 2 · Run a refund the agent has to refuse
#
# `ord_a6` is a EUR 620 frame; the policy caps refunds at EUR 500. The instructions send the agent to
# the advisor before it refuses, and to the sidekick for the closing note. The loop is module 08's:
# execute the `function_call` items that are ours, skip the ones with an `orq:*` sibling (the
# platform already ran those), continue with `previous_response_id`.


# %%
def run_agent(
    agent: str, text: str, *, store: OrderStore | None = None, max_steps: int = 8, **kw: Any
) -> dict[str, Any]:
    """One customer turn. Keeps every output item of the chain, so step 3 can read the delegation."""
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
    return {
        "text": text_out,
        "tool_calls": called,
        "traces": traces,
        "items": items,
        "usage": r["usage"],
    }


t0 = time.time()
out = run_agent(AGENT, QUESTION)
delegated = [o["type"][4:] for o in out["items"] if o["type"] in ("orq:advisor", "orq:sidekick")]
print(
    f"[2] tools={out['tool_calls']} delegated={delegated} steps={len(out['traces'])} {time.time() - t0:.1f}s"
)
print(f"    answer: {out['text'][:160]}")
print(f"    $ orq traces thread {out['traces'][-1]}")

# %% [markdown]
# ## Step 3 · Read what each tool sent and got back
#
# Both tools show up twice in the output: a `function_call` item with the arguments the agent wrote,
# then an `orq:advisor` / `orq:sidekick` item with the result. The advisor's arguments are a question
# (the platform adds the transcript); the sidekick's are the task and nothing else. That is the whole
# difference between the two, and the reason a sidekick is the wrong tool for a judgement.

# %%
calls = {o["call_id"]: o for o in out["items"] if o["type"] == "function_call"}
for o in out["items"]:
    if o["type"] in ("orq:advisor", "orq:sidekick"):
        args = json.loads(calls[o["call_id"]]["arguments"] or "{}") if o["call_id"] in calls else {}
        sent = args.get("question") or args.get("task") or json.dumps(args)
        print(f"[3] {o['type']:<13} sent: {sent[:110]!r}")
        print(f"                  got:  {str(o.get('result'))[:110]!r}")

# %% [markdown]
# ## Step 4 · Read the cost split in the trace
#
# Each secondary call goes through the AI Gateway on its own, so it is metered on its own and
# appears as a nested span: `advisor` (span.tool) > `chat gpt-5.6-sol`, `sidekick` > `chat gpt-5.4-nano`.
# Sum the agent's own `chat openai/gpt-5.6-luna` spans and compare. This is the number that says
# whether the escalation was worth it.

# %%
time.sleep(5)  # nested tool spans arrive a few seconds after the response
rows: list[tuple[str, str, float]] = []  # (owner, model, cost)
for tid in out["traces"]:
    spans = [s.model_dump(by_alias=True) for s in orq.traces.list_spans(trace_id=tid).data or []]
    parent = {s["span_id"]: s for s in spans}
    for s in spans:
        if (
            s["cost"]["total"] <= 0 or s["type"] == "trace"
        ):  # the root repeats the agent's own model cost
            continue
        p = parent.get(s.get("parent_span_id") or "")
        owner = p["name"] if p and p["type"] == "span.tool" else "agent"
        rows.append((owner, s["model"], s["cost"]["total"]))
total = sum(c for _, _, c in rows) or 1
print(f"[4] cost split over {len(out['traces'])} traces, ${total:.5f} total")
for owner in ("agent", "advisor", "sidekick"):
    part = [r for r in rows if r[0] == owner]
    if part:
        print(
            f"    {owner:<9} {part[0][1]:<14} calls={len(part)}  ${sum(c for _, _, c in part):.5f}  {100 * sum(c for _, _, c in part) / total:5.1f}%"
        )
print(
    f"    $ orq traces get-span {out['traces'][-1]} <span_id>   # any row above, or open the trace in the Studio"
)

# %% [markdown]
# ## Step 5 · When the secondary model fails
#
# A copy of the agent points its advisor at a model that does not exist. The turn does not fail:
# the `orq:advisor` item carries the error text, the advisor span stays `ok`, and the agent answers
# from its own model. So a broken advisor degrades quality silently. Alert on the advisor's error
# text, or on `genai.error_rate` filtered to the advisor's model (module 14), not on the agent.

# %%
try:
    orq.agents.retrieve(agent_key=BROKEN)
except Exception:  # noqa: BLE001
    ensure_delegating_agent(
        name="refund-agent-delegating-broken", advisor_model="openai/gpt-does-not-exist"
    )
    print(f"    created {BROKEN}")
bad = run_agent(BROKEN, QUESTION)
adv = next((o for o in bad["items"] if o["type"] == "orq:advisor"), None)
print(f"[5] {BROKEN}: tools={bad['tool_calls']} answered={bool(bad['text'])}")
print(f"    orq:advisor result: {str(adv.get('result') if adv else None)[:110]!r}")
time.sleep(5)
for tid in bad["traces"]:
    adv_spans = [s for s in orq.traces.list_spans(trace_id=tid).data or [] if s.name == "advisor"]
    if adv_spans:
        print(
            f"    trace {tid}: {len(adv_spans)} advisor span(s), status={adv_spans[0].status} cost=${sum(s.cost.total for s in adv_spans):.5f}, no chat span underneath"
        )

# %% [markdown]
# ## Step 6 · The same from the CLI
#
# ```bash
# orq agents retrieve ws-refund-agent-delegating -o json | jq '.settings.tools[] | select(.action_type == "advisor" or .action_type == "sidekick") | {action_type, configuration}'
# orq responses create --model agent/ws-refund-agent-delegating --input '"Refund ord_a6 please, the frame arrived scratched."' -o json | jq '[.output[] | select(.type | startswith("orq:")) | {type, result}]'
# ```

# %%
print(
    f"open {settings.base_url}/traces and search {out['traces'][-1]}: the advisor and sidekick spans sit under agent.response with their own cost"
)
