# %% [markdown]
# # 03 · Smart routing and routing rules
#
# Let the gateway pick the model, then override it with a rule. `MODEL=openai/gpt-5.6-luna` in `.env` is a guess frozen at deploy time; a Smart Router grades each request and picks from a pool, and a routing rule pins traffic that matches a CEL expression to a target. Both leave a span in the trace. Four steps: create the router and watch it pick on an easy and a hard prompt, switch its profile, redirect tagged traffic with a rule, repeat it from the CLI.
#
# | | |
# |---|---|
# | **Time** | 20 min |
# | **Prerequisites** | module 01 |
# | **You will have** | a Smart Router `ws-refund-router` the refund agent calls by reference, traces that show which model it picked and why, and a routing rule that redirects cheap-tier traffic to `gpt-5.4-nano` |
#
# This file is both the solution script (`make m03`) and the notebook source (`make notebooks`).
# Run the cells top to bottom; step 3 disables and deletes what it created.

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
POOL = [
    "openai/gpt-5.6-luna",
    "openai/gpt-5.4-nano",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-sol",
    "anthropic/claude-haiku-4-5-20251001",
]
COST_PROFILE = "SMART_ROUTER_PROFILE_COST"
QUALITY_PROFILE = "SMART_ROUTER_PROFILE_QUALITY"
RULE_TARGET = "openai/gpt-5.4-nano"
RULE_PROPAGATION_SECONDS = 10  # a new or updated rule takes a few seconds to reach the gateway
MODEL_SPAN_TYPES = ("span.chat_completion", "span.responses")  # chat completions vs Responses endpoint
ROUTING_SPAN_TYPES = ("span.auto_router", "span.load_balancer")  # a smart router pick vs a rule redirect
TRACES_URL = f"{settings.base_url}/traces"
EASY = "What is your refund window? One sentence."
HARD = (
    "I ordered ord_a5 70 days ago; the box arrived crushed but I only opened it now. Walk me through every "
    "policy clause that applies, check the order, and decide whether a post-window exception is warranted."
)


def spans(trace_id: str) -> list[dict[str, Any]]:
    """Span summaries of one trace. Hides the wait: the gateway indexes a trace a few seconds after the call."""
    for _ in range(6):
        time.sleep(4)
        rows = orq.traces.list_spans(trace_id=trace_id).model_dump(by_alias=True)["data"]
        if rows:
            return rows
    return []


def model_used(trace_id: str) -> tuple[str, float, bool]:
    """(model, cost, routed) read from the trace, not from the response. `routed` is True when a router or rule span is present."""
    rows = spans(trace_id)
    model_spans = [span for span in rows if span["type"] in MODEL_SPAN_TYPES]
    routed = any(span["type"] in ROUTING_SPAN_TYPES for span in rows)
    model = model_spans[-1]["model"] if model_spans else "?"
    cost = sum((span.get("cost") or {}).get("total") or 0 for span in model_spans)
    return model, cost, routed


def run_pair(model_ref: str) -> None:
    """Send the easy and the hard prompt to `model_ref` and print who answered each, read from the trace."""
    for label, prompt in (("easy", EASY), ("hard", HARD)):
        result = chat(prompt, model=model_ref)
        model, cost, routed = model_used(result.trace_id)
        print(f"{label:8} : {model:28} ${cost:.6f}  auto_router={routed}  trace={result.trace_id}")


def ensure_router() -> dict[str, Any]:
    """Find the router by key, or create it with the COST profile. Keys are unique per workspace, so find first."""
    for router in orq.smart_routers.list(search=ROUTER_KEY, limit=50).model_dump(by_alias=True)["data"]:
        if router["key"] == ROUTER_KEY:
            return router
    created = orq.smart_routers.create(key=ROUTER_KEY, models=POOL, profile=COST_PROFILE)
    return created.model_dump(by_alias=True)["smart_router"]


def normalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the create/update envelope and expose `id`: list items dump as `_id`, create and update responses as `id`."""
    rule = rule.get("routing_rule", rule)
    rule["id"] = rule.get("id") or rule.get("_id")
    return rule


def ensure_rule(display_name: str, project_id: str | None, cel: str) -> dict[str, Any]:
    """Find the rule by name (re-enabling it with the given CEL), or create it. `project_id=None` means workspace-wide."""
    # rules_api = the SDK call, or `orq request` when the key gets 403 (admin-only endpoint since 4.14.17)
    scope = f"&project_id={project_id}" if project_id else ""
    for rule in rules_api("GET", f"/v2/routing-rules?limit=50&search={display_name}{scope}").get("data") or []:
        if rule["display_name"] == display_name:
            rule_id = rule.get("_id") or rule["id"]
            patch = {"enabled": True, "expression": {"cel": cel}}
            return normalize_rule(rules_api("PATCH", f"/v2/routing-rules/{rule_id}", patch))
    body: dict[str, Any] = {
        "display_name": display_name,
        "description": "workshop module 03: send cheap-tier traffic to gpt-5.4-nano",
        "enabled": True,
        "expression": {"cel": cel},
        "models_config": {"mode": "weighted", "models": [{"model": RULE_TARGET, "weight": 1.0}]},
        "priority": 50,
    }
    if project_id:
        body["project_id"] = project_id
    return normalize_rule(rules_api("POST", "/v2/routing-rules", body))

# %% [markdown]
# ## Step 1 · Create the router and watch it pick
#
# A smart router is a pool of models plus a profile. Find first, then create: the key is unique
# per workspace. The app then asks for the router's `model_ref` instead of a model id. The model
# that answered is read from the trace, not from the response: `span.auto_router` is followed by a
# `span.responses` (or `span.chat_completion`) with the chosen model.
#
# Pick 3 or 4 models that are enabled in your workspace:
# `orq models list -o json | jq -r '.[] | select(.enabled) | .provider + "/" + .model_id'`.

# %%
router = ensure_router()
if router["profile"] != COST_PROFILE:
    # a previous run left it on QUALITY; start every run from the same profile
    updated = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile=COST_PROFILE)
    router = updated.model_dump(by_alias=True)["smart_router"]

print("── Step 1 · Create the router and watch it pick ───────")
print(f"router   : {router['model_ref']}")
print(f"profile  : {router['profile']}")
print(f"pool     : {', '.join(router['models'])}")
run_pair(router["model_ref"])
print("next     : open the hard trace; the span.auto_router span carries the band the request landed in")

# %% [markdown]
# Open the hard trace in the Studio: the router span carries the band the request landed in.
#
# ## Step 2 · Switch the profile
#
# The key and `model_ref` do not change, so the app does not either. Expect the easy question to
# move one band up; the hard one usually stays on the model the router already trusted.

# %%
updated = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile=QUALITY_PROFILE)
router = updated.model_dump(by_alias=True)["smart_router"]

print("── Step 2 · Switch the profile ────────────────────────")
print(f"router   : {router['model_ref']} (same model_ref, the app did not change)")
print(f"profile  : {router['profile']}")
run_pair(router["model_ref"])
print("next     : compare with step 1; the pick moves only when two pool models are close in band")

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
project_cel = 'metadata["tier"] == "free" && model == "openai/gpt-5.6-luna"'  # CEL reads metadata as a map: metadata.tier is rejected
free_tier_body = {"metadata": {"tier": "free"}}

project_rule = ensure_rule(settings.key("route-mini-to-nano"), PROJECT_ID, project_cel)
try:
    time.sleep(RULE_PROPAGATION_SECONDS)
    result = chat(EASY, extra_body=free_tier_body)
    model, _, rule_fired = model_used(result.trace_id)
finally:
    # Disable even when the call or the trace lookup raised: a live rule must not outlive the script.
    rules_api("PATCH", f"/v2/routing-rules/{project_rule['id']}", {"enabled": False})

print("── Step 3a · A project-scoped routing rule ────────────")
print(f"rule     : {project_rule['id']} (project {project_rule['project_id']})")
print(f"cel      : {project_cel}")
print(f"target   : {RULE_TARGET}")
print(f"call     : metadata tier=free, model {settings.model}")
print(f"answered : {model}")
print(f"trace    : {result.trace_id}")
if rule_fired:
    print(f"verdict  : rule fired: {model} answered a request that asked for {settings.model}")
else:
    print("verdict  : rule did not fire: a plain router call carries no project scope, so a project rule never sees it")
print(f"disabled : {project_rule['id']} (kept in place for module 08)")

# %% [markdown]
# A workspace-wide rule gated on our own metadata key touches nobody else's traffic. One tagged
# call and one untagged call show the rule matching on the tag alone; the rule is deleted right after.

# %%
workspace_cel = 'metadata["ws_module"] == "03" && model == "openai/gpt-5.6-luna"'
workspace_rule = ensure_rule(settings.key("route-mini-to-nano-ws"), None, workspace_cel)
try:
    time.sleep(RULE_PROPAGATION_SECONDS)
    tagged = chat(EASY, extra_body={"metadata": {"ws_module": "03"}})
    untagged = chat(EASY, extra_body={"metadata": {"ws_module": "no"}})
    tagged_model, _, tagged_fired = model_used(tagged.trace_id)
    untagged_model, _, untagged_fired = model_used(untagged.trace_id)
finally:
    # A workspace-wide rule touches everyone's traffic: disable and delete it whatever happened above.
    rules_api("PATCH", f"/v2/routing-rules/{workspace_rule['id']}", {"enabled": False})
    rules_api("DELETE", f"/v2/routing-rules/{workspace_rule['id']}")

print("── Step 3b · A workspace-wide rule, gated on a tag ────")
print(f"rule     : {workspace_rule['id']} (workspace-wide)")
print(f"cel      : {workspace_cel}")
print(f"tagged   : ws_module=03 → {tagged_model:14} rule_fired={tagged_fired}  trace={tagged.trace_id}")
print(f"untagged : ws_module=no → {untagged_model:14} rule_fired={untagged_fired}  trace={untagged.trace_id}")
if tagged_fired and not untagged_fired:
    print(f"verdict  : rule fired on the tag alone: {tagged_model} answered a request that asked for {settings.model}")
else:
    print("verdict  : unexpected: check the rule in the Studio and rerun the cell")
print(f"deleted  : {workspace_rule['id']}")
print("next     : open the tagged trace; a span.load_balancer span records the rule's target")

# %% [markdown]
# The request asked for `gpt-5.6-luna`; a `span.load_balancer` span records the rule's target and
# `gpt-5.4-nano` answered. The project rule stays in place, disabled, for module 08.
#
# ## Step 4 · The same from the CLI
#
# `orq smart-routers create --example` and `orq request POST /v2/routing-rules` take the same
# bodies the SDK sends.

# %%
print("── Step 4 · The same from the CLI ─────────────────────")
print("routers  : orq smart-routers list -o json | jq '.data[] | {key, profile, models}'")
print(f"rules    : orq request GET '/v2/routing-rules?project_id={PROJECT_ID}' -o json | jq '.body.data[] | {{_id, display_name, enabled, expression}}'")
print(f"next     : open {TRACES_URL} and look for span.auto_router and span.load_balancer")
