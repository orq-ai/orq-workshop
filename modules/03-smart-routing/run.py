"""Module 03 starter: let the gateway pick the model, then override it with a rule.

Factor 8: own your control flow. The app asks for `<workspace>@orq/ws-refund-router`; which model answers is a
decision you can read in the trace (`span.auto_router`) and change without a deploy (profile, routing rule).

Fill in the TODOs. The script runs as is; a step with an unfilled TODO says so in its output block.
Run it with `uv run python modules/03-smart-routing/run.py`.
"""

from __future__ import annotations

import time
from typing import Any

from app.refund_agent.agent import chat
from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

orq = make_orq()
PROJECT_ID = "01a082d7-b8cc-7c86-bfe8-83f9cb47688b"  # orq-workshop; `orq projects list -o json` shows yours
ROUTER_KEY = settings.key("refund-router")
POOL: list[str] = []  # TODO: 3 to 4 enabled models, e.g. openai/gpt-5.6-luna, openai/gpt-5.4-nano, openai/gpt-5.6-terra, openai/gpt-5.6-sol, anthropic/claude-haiku-4-5-20251001
COST_PROFILE = "SMART_ROUTER_PROFILE_COST"
QUALITY_PROFILE = "SMART_ROUTER_PROFILE_QUALITY"
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


def ensure_router() -> dict[str, Any]:
    """Find the router by key, or create it. Keys are unique per workspace, so find first."""
    for router in orq.smart_routers.list(search=ROUTER_KEY, limit=50).model_dump(by_alias=True)["data"]:
        if router["key"] == ROUTER_KEY:
            return router
    if not POOL:
        raise SystemExit("fill POOL first (Step 1)")
    # TODO: orq.smart_routers.create(key=ROUTER_KEY, models=POOL, profile=COST_PROFILE).model_dump(by_alias=True)["smart_router"]
    raise SystemExit("create the router (Step 1)")


def run_pair(model_ref: str) -> None:
    """Send the easy and the hard prompt to `model_ref` and print who answered each, read from the trace."""
    for label, prompt in (("easy", EASY), ("hard", HARD)):
        result = chat(prompt, model=model_ref)
        model, cost, routed = model_used(result.trace_id)
        print(f"{label:8} : {model:28} ${cost:.6f}  auto_router={routed}  trace={result.trace_id}")


# ── Step 1 · Create the router and watch it pick ──
# A smart router is a pool of models plus a profile. The app asks for its model_ref instead of a
# model id; the model that answered is read from the trace (span.auto_router, then the model span).
def step_1_cost_profile() -> dict[str, Any]:
    """Create or find the router, then send the easy and the hard prompt to it."""
    router = ensure_router()

    print("── Step 1 · Create the router and watch it pick ───────")
    if not POOL:
        print("TODO     : fill in POOL with 3 to 4 enabled models, then rerun")
    print(f"router   : {router['model_ref']}")
    print(f"profile  : {router['profile']}")
    print(f"pool     : {', '.join(router['models'])}")
    run_pair(router["model_ref"])
    print("next     : open the hard trace; the span.auto_router span carries the band the request landed in")
    return router


# ── Step 2 · Switch the profile ──
# The key and model_ref do not change, so the app does not either. Only the router's preference
# between close bands moves.
def step_2_quality_profile(router: dict[str, Any]) -> None:
    """Switch the router to the QUALITY profile and send the same two prompts."""
    # TODO: router = orq.smart_routers.update(smart_router_id=router["smart_router_id"], profile=QUALITY_PROFILE).model_dump(by_alias=True)["smart_router"]

    print("── Step 2 · Switch the profile ────────────────────────")
    if router["profile"] != QUALITY_PROFILE:
        print("TODO     : update the router to the QUALITY profile, then rerun")
    print(f"router   : {router['model_ref']} (same model_ref, the app did not change)")
    print(f"profile  : {router['profile']}")
    run_pair(router["model_ref"])
    print("next     : compare with step 1; the pick moves only when two pool models are close in band")


# ── Step 3 · Pin traffic with a routing rule ──
# A rule is a CEL match plus a target. Fields: model, metadata["k"], identity, headers["h"], project.
# Always pass project_id: a workspace-wide rule affects everyone's traffic.
def step_3_routing_rule() -> None:
    """Create a rule that sends free-tier calls to gpt-5.4-nano, prove it on a tagged call, disable it."""
    cel = ""  # TODO: 'metadata["tier"] == "free" && model == "openai/gpt-5.6-luna"'  (CEL reads metadata as a map: metadata.tier is rejected)
    # TODO: orq.routing_rules.create(display_name=settings.key("route-mini-to-nano"), project_id=PROJECT_ID, enabled=True,
    #       expression={"cel": cel}, models_config={"mode": "weighted", "models": [{"model": "openai/gpt-5.4-nano", "weight": 1.0}]}, priority=50)
    # Then call chat(EASY, extra_body={"metadata": {"tier": "free"}}) and read model_used(); disable the rule at the end.

    print("── Step 3 · Pin traffic with a routing rule ───────────")
    if not cel:
        print("TODO     : fill in `cel`, create the rule, send a tagged call and read model_used(), then rerun")
    print(f"cel      : {cel!r}")
    print("target   : openai/gpt-5.4-nano")
    print("next     : open the tagged trace; a span.load_balancer span records the rule's target")


# ── Step 4 · The same from the CLI ──
# The CLI takes the same bodies the SDK sends.
def step_4_cli() -> None:
    """The two commands that list what this module created."""
    print("── Step 4 · The same from the CLI ─────────────────────")
    print("routers  : orq smart-routers list -o json | jq '.data[] | {key, profile, models}'")
    print(f"rules    : orq request GET '/v2/routing-rules?project_id={PROJECT_ID}' -o json | jq '.body.data[] | {{_id, display_name, enabled, expression}}'")
    print(f"next     : open {TRACES_URL} and look for span.auto_router and span.load_balancer")


if __name__ == "__main__":
    router = step_1_cost_profile()
    step_2_quality_profile(router)
    step_3_routing_rule()
    step_4_cli()
