"""Module 03 solution: let the gateway pick the model, then override it with a rule.

Factor 8: own your control flow. The app asks for `<workspace>@orq/ws-refund-router`; which model answers is a
decision you can read in the trace (`span.auto_router`) and change without a deploy (profile, routing rule).
"""

from __future__ import annotations

import time
from typing import Any

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

orq = make_orq()
PROJECT_ID = "01a082d7-b8cc-7c86-bfe8-83f9cb47688b"  # orq-workshop; `orq projects list --json` shows yours
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


def ensure_router() -> dict[str, Any]:
    """Find first, then create. The key is unique per workspace."""
    for r in orq.smart_routers.list(search=ROUTER_KEY, limit=50).model_dump(by_alias=True)["data"]:
        if r["key"] == ROUTER_KEY:
            return r
    return orq.smart_routers.create(key=ROUTER_KEY, models=POOL, profile="SMART_ROUTER_PROFILE_COST").model_dump(by_alias=True)["smart_router"]


def run_pair(label: str, model_ref: str) -> None:
    for name, prompt in (("easy", EASY), ("hard", HARD)):
        r = chat(prompt, model=model_ref)
        model, cost, routed = model_used(r.trace_id)
        print(f"    {name:4} -> {model:28} ${cost:.6f}  auto_router={routed}  trace={r.trace_id}")


def step_1_cost_profile() -> dict[str, Any]:
    router = ensure_router()
    if router["profile"] != "SMART_ROUTER_PROFILE_COST":
        router = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile="SMART_ROUTER_PROFILE_COST").model_dump(by_alias=True)["smart_router"]
    print(f"[1] smart router   {router['model_ref']}  profile=COST  pool={router['models']}")
    run_pair("cost", router["model_ref"])
    return router


def step_2_quality_profile(router: dict[str, Any]) -> None:
    router = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile="SMART_ROUTER_PROFILE_QUALITY").model_dump(by_alias=True)["smart_router"]
    print(f"[2] profile        {router['profile']}")
    run_pair("quality", router["model_ref"])


def ensure_rule(display_name: str, project_id: str | None, cel: str) -> dict[str, Any]:
    rules = orq.routing_rules.list(project_id=project_id, search=display_name, limit=50).model_dump(by_alias=True)["data"]
    for r in rules:
        if r["display_name"] == display_name:  # list items dump as `_id`, create/update as `id`
            rid = r.get("id") or r["_id"]
            return _norm(orq.routing_rules.update(routing_rule_id=rid, enabled=True, expression={"cel": cel}).model_dump(by_alias=True))
    return _norm(orq.routing_rules.create(
        display_name=display_name,
        description="workshop module 03: send cheap-tier traffic to gpt-4.1-nano",
        project_id=project_id,
        enabled=True,
        expression={"cel": cel},
        models_config={"mode": "weighted", "models": [{"model": "openai/gpt-4.1-nano", "weight": 1.0}]},
        priority=50,
    ).model_dump(by_alias=True))


def _norm(rule: dict[str, Any]) -> dict[str, Any]:
    rule["id"] = rule.get("id") or rule.get("_id")
    return rule


def step_3_routing_rule() -> None:
    """A rule is a CEL match plus a target. Fields: model, metadata["k"], identity, headers["h"], project."""
    cel = 'metadata["tier"] == "free" && model == "openai/gpt-4o-mini"'
    body = {"metadata": {"tier": "free"}}

    project_rule = ensure_rule(settings.key("route-mini-to-nano"), PROJECT_ID, cel)
    time.sleep(10)
    r = chat(EASY, extra_body=body)
    model, _, routed = model_used(r.trace_id)
    print(f"[3] project rule   {project_rule['id']} project={project_rule['project_id']} cel={cel}")
    print(f"    tier=free call -> {model:28} rule_fired={routed}  trace={r.trace_id}")
    orq.routing_rules.update(routing_rule_id=project_rule["id"], enabled=False)

    # Raw router calls carry no project scope in this workspace, so a project rule never sees them (see README).
    # A workspace-wide rule gated on our own metadata key touches nobody else's traffic. Deleted at the end.
    cel_ws = 'metadata["ws_module"] == "03" && model == "openai/gpt-4o-mini"'
    ws_rule = ensure_rule(settings.key("route-mini-to-nano-ws"), None, cel_ws)
    time.sleep(10)
    r_hit = chat(EASY, extra_body={"metadata": {"ws_module": "03"}})
    r_miss = chat(EASY, extra_body={"metadata": {"ws_module": "no"}})
    for label, rr in (("ws_module=03", r_hit), ("ws_module=no", r_miss)):
        model, _, routed = model_used(rr.trace_id)
        print(f"    workspace rule {ws_rule['id']} {label:13} -> {model:14} rule_fired={routed}  trace={rr.trace_id}")
    orq.routing_rules.update(routing_rule_id=ws_rule["id"], enabled=False)
    orq.routing_rules.delete(routing_rule_id=ws_rule["id"])
    print(f"    disabled {project_rule['id']}, deleted {ws_rule['id']}")


def step_4_cli() -> None:
    print("[4] CLI            orq smart-routers list --json | jq '.data[] | {key, profile, models}'")
    print("                   orq request GET '/v2/routing-rules?project_id=" + PROJECT_ID + "' --json | jq '.body.data[] | {_id, display_name, enabled, expression}'")


if __name__ == "__main__":
    router = step_1_cost_profile()
    step_2_quality_profile(router)
    step_3_routing_rule()
    step_4_cli()
    print(f"open {settings.base_url}/traces and look for span.auto_router and span.load_balancer")
