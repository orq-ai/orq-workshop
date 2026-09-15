# %% [markdown]
# # 03 · Smart routing and routing rules
#
# Let the gateway pick the model, then override it with a rule. `MODEL=openai/gpt-4o-mini` in `.env` is a guess frozen at deploy time; a Smart Router grades each request and picks from a pool, and a routing rule pins traffic that matches a CEL expression to a target. Both leave a span in the trace. Four steps: create the router and watch it pick on an easy and a hard prompt, switch its profile, redirect tagged traffic with a rule, repeat it from the CLI.
#
# | | |
# |---|---|
# | **Time** | 20 min |
# | **Prerequisites** | module 01 |
# | **You will have** | a Smart Router `ws-refund-router` the refund agent calls by reference, traces that show which model it picked and why, and a routing rule that redirects cheap-tier traffic to `gpt-4.1-nano` |
#
# This file is both the solution script (`make m03`) and the notebook source (`make notebooks`).
# Run the cells top to bottom; the last step disables and deletes what it created.

# %%
from __future__ import annotations

import time
from typing import Any

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import rules_api

orq = make_orq()
PROJECT_ID = "01a082d7-b8cc-7c86-bfe8-83f9cb47688b"  # orq-workshop; `orq projects list -o json` shows yours
ROUTER_KEY = settings.key("refund-router")
POOL = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini", "openai/gpt-4.1", "anthropic/claude-haiku-4-5-20251001"]
EASY = "What is your refund window? One sentence."
HARD = (
    "I ordered ord_a5 70 days ago; the box arrived crushed but I only opened it now. Walk me through every "
    "policy clause that applies, check the order, and decide whether a post-window exception is warranted."
)


def spans(trace_id: str) -> list[dict[str, Any]]:
    for _ in range(6):
        time.sleep(4)
        data = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
        if data:
            return data
    return []


def model_used(trace_id: str) -> tuple[str, float, bool]:
    """(model, cost, routed) from the trace. `routed` is True when a router or rule span is present."""
    rows = spans(trace_id)
    llm = [s for s in rows if s["type"] == "span.chat_completion"]
    routed = any(s["type"] in ("span.auto_router", "span.load_balancer") for s in rows)
    model = llm[-1]["model"] if llm else "?"
    cost = sum((s.get("cost") or {}).get("total") or 0 for s in llm)
    return model, cost, routed


def run_pair(label: str, model_ref: str) -> None:
    for name, prompt in (("easy", EASY), ("hard", HARD)):
        r = chat(prompt, model=model_ref)
        model, cost, routed = model_used(r.trace_id)
        print(f"    {name:4} -> {model:28} ${cost:.6f}  auto_router={routed}  trace={r.trace_id}")

# %% [markdown]
# ## Step 1 · Create the router and watch it pick
#
# A smart router is a pool of models plus a profile. Find first, then create: the key is unique
# per workspace. The app then asks for the router's `model_ref` instead of a model id. The model
# that answered is read from the trace, not from the response: `span.auto_router` is followed by a
# `span.chat_completion` with the chosen model.
#
# Pick 3 or 4 models that are enabled in your workspace:
# `orq models list -o json | jq -r '.[] | select(.enabled) | .provider + "/" + .model_id'`.

# %%
def ensure_router() -> dict[str, Any]:
    for r in orq.smart_routers.list(search=ROUTER_KEY, limit=50).model_dump(by_alias=True)["data"]:
        if r["key"] == ROUTER_KEY:
            return r
    return orq.smart_routers.create(key=ROUTER_KEY, models=POOL, profile="SMART_ROUTER_PROFILE_COST").model_dump(by_alias=True)["smart_router"]


router = ensure_router()
if router["profile"] != "SMART_ROUTER_PROFILE_COST":
    router = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile="SMART_ROUTER_PROFILE_COST").model_dump(by_alias=True)["smart_router"]
print(f"[1] smart router   {router['model_ref']}  profile=COST  pool={router['models']}")
run_pair("cost", router["model_ref"])

# %% [markdown]
# Open the hard trace in the Studio: the router span carries the band the request landed in.
#
# ## Step 2 · Switch the profile
#
# The key and `model_ref` do not change, so the app does not either. Expect the easy question to
# move one band up; the hard one usually stays on the model the router already trusted.

# %%
router = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile="SMART_ROUTER_PROFILE_QUALITY").model_dump(by_alias=True)["smart_router"]
print(f"[2] profile        {router['profile']}")
run_pair("quality", router["model_ref"])

# %% [markdown]
# ## Step 3 · Pin traffic with a routing rule
#
# A rule is a CEL match plus a target. Fields you can match: `model`, `metadata["k"]`, `identity`,
# `headers["h"]`, `project`. Always pass `project_id`: a workspace-wide rule affects everyone's
# traffic.
#
# Two things will happen. The project-scoped rule is created and validated but does not match: in
# this workspace a plain router call carries no project scope (its trace has an empty
# `project_id`), and a project rule only sees requests that have one, such as the agent calls of
# module 08. So the redirect is proved with a workspace-wide rule gated on a metadata key nobody
# else sends, and deleted right after.

# %%
def ensure_rule(display_name: str, project_id: str | None, cel: str) -> dict[str, Any]:
    # rules_api = the SDK call, or `orq request` when the key gets 403 (admin-only endpoint since 4.14.17)
    scope = f"&project_id={project_id}" if project_id else ""
    for r in rules_api("GET", f"/v2/routing-rules?limit=50&search={display_name}{scope}").get("data") or []:
        if r["display_name"] == display_name:
            rid = r.get("_id") or r["id"]
            return _norm(rules_api("PATCH", f"/v2/routing-rules/{rid}", {"enabled": True, "expression": {"cel": cel}}))
    body: dict[str, Any] = {
        "display_name": display_name,
        "description": "workshop module 03: send cheap-tier traffic to gpt-4.1-nano",
        "enabled": True,
        "expression": {"cel": cel},
        "models_config": {"mode": "weighted", "models": [{"model": "openai/gpt-4.1-nano", "weight": 1.0}]},
        "priority": 50,
    }
    if project_id:
        body["project_id"] = project_id
    return _norm(rules_api("POST", "/v2/routing-rules", body))


def _norm(rule: dict[str, Any]) -> dict[str, Any]:
    rule = rule.get("routing_rule", rule)
    rule["id"] = rule.get("id") or rule.get("_id")
    return rule


cel = 'metadata["tier"] == "free" && model == "openai/gpt-4o-mini"'
body = {"metadata": {"tier": "free"}}

project_rule = ensure_rule(settings.key("route-mini-to-nano"), PROJECT_ID, cel)
time.sleep(10)
r = chat(EASY, extra_body=body)
model, _, routed = model_used(r.trace_id)
print(f"[3] project rule   {project_rule['id']} project={project_rule['project_id']} cel={cel}")
print(f"    tier=free call -> {model:28} rule_fired={routed}  trace={r.trace_id}")
rules_api("PATCH", f"/v2/routing-rules/{project_rule['id']}", {"enabled": False})

# %%
# A workspace-wide rule gated on our own metadata key touches nobody else's traffic. Deleted below.
cel_ws = 'metadata["ws_module"] == "03" && model == "openai/gpt-4o-mini"'
ws_rule = ensure_rule(settings.key("route-mini-to-nano-ws"), None, cel_ws)
time.sleep(10)
r_hit = chat(EASY, extra_body={"metadata": {"ws_module": "03"}})
r_miss = chat(EASY, extra_body={"metadata": {"ws_module": "no"}})
for label, rr in (("ws_module=03", r_hit), ("ws_module=no", r_miss)):
    model, _, routed = model_used(rr.trace_id)
    print(f"    workspace rule {ws_rule['id']} {label:13} -> {model:14} rule_fired={routed}  trace={rr.trace_id}")
rules_api("PATCH", f"/v2/routing-rules/{ws_rule['id']}", {"enabled": False})
rules_api("DELETE", f"/v2/routing-rules/{ws_rule['id']}")
print(f"    disabled {project_rule['id']}, deleted {ws_rule['id']}")

# %% [markdown]
# The request asked for `gpt-4o-mini`; a `span.load_balancer` span records the rule's target and
# `gpt-4.1-nano` answered. The project rule stays in place, disabled, for module 08.
#
# ## Step 4 · The same from the CLI
#
# `orq smart-routers create --example` and `orq request POST /v2/routing-rules` take the same
# bodies the SDK sends.

# %%
print("[4] CLI            orq smart-routers list -o json | jq '.data[] | {key, profile, models}'")
print("                   orq request GET '/v2/routing-rules?project_id=" + PROJECT_ID + "' -o json | jq '.body.data[] | {_id, display_name, enabled, expression}'")
print(f"open {settings.base_url}/traces and look for span.auto_router and span.load_balancer")
