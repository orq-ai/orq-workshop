# 03 · Smart routing

!!! abstract "Factor 8: Own your control flow"
    Which model answers is a decision. This module moves that decision out of the code and into two places you can read and change at runtime: a Smart Router that picks per request, and a routing rule that overrides it.

**Time:** 20 min · **Prereqs:** module 01 · **You will have:** a Smart Router `ws-refund-router` the refund agent calls by reference, traces that show which model it picked and why, and a routing rule that redirects cheap-tier traffic to `gpt-4.1-nano`.

## Why

`MODEL=openai/gpt-4o-mini` in `.env` is a guess frozen at deploy time. Easy questions overpay on a strong model, hard ones underdeliver on a cheap one. A Smart Router grades each request and picks from a pool; a routing rule pins traffic that matches a CEL expression to a target. Both leave a span in the trace, so the decision is auditable.

## The one concept to understand first

A Smart Router is a model id. `orq.smart_routers.create(key=..., models=[...], profile=...)` returns `model_ref` like `orq-research@orq/ws-refund-router`; you pass that where you passed `openai/gpt-4o-mini`. The profile (`COST`, `BALANCED`, `QUALITY`) shifts how aggressively it prefers the cheap band. The trace gets a `span.auto_router` span and the `span.chat_completion` below it names the winner.

A routing rule sits in front of that: `expression.cel` decides if it applies, `models_config` says where the request goes instead. The CEL variables are `model`, `metadata["key"]`, `identity`, `headers["name"]` and `project`. When a rule matches it replaces the request's `model`, `load_balancer` and `fallbacks` entirely.

```python
router = orq.smart_routers.create(key="ws-refund-router", models=POOL, profile="SMART_ROUTER_PROFILE_COST").smart_router
chat("What is your refund window?", model=router.model_ref)

orq.routing_rules.create(display_name="ws-route-mini-to-nano", project_id=PROJECT_ID, enabled=True,
    expression={"cel": 'metadata["tier"] == "free" && model == "openai/gpt-4o-mini"'},
    models_config={"mode": "weighted", "models": [{"model": "openai/gpt-4.1-nano", "weight": 1.0}]}, priority=50)
```

## Steps

Open `modules/03-smart-routing/run.py`. Fill the `TODO`s; the solution is in `solution/run.py`.

### Step 1 · Create the router and watch it pick

Pick 3 or 4 enabled models. `orq models list --json | jq -r '.[] | select(.enabled) | .provider + "/" + .model_id'` lists what is enabled in your workspace (the ids in the pool below were). Create with profile `COST`, then send one easy and one hard prompt to the `model_ref`.

```bash
$ uv run python modules/03-smart-routing/run.py
```

Expected output:

```text
[1] smart router   orq-research@orq/ws-refund-router  profile=COST  pool=['openai/gpt-4o-mini', 'openai/gpt-4.1-mini', 'openai/gpt-4.1', 'anthropic/claude-haiku-4-5-20251001']
    easy -> gpt-4o-mini                  $0.000128  auto_router=True  trace=6c811026b419bef410a974cfda4fb17f
    hard -> claude-haiku-4-5-20251001    $0.003568  auto_router=True  trace=75f037d83440d2a495684979a02c635f
```

The model is read from the trace, not from the response: `orq.traces.list_spans(trace_id=...)` returns `span.auto_router` followed by `span.chat_completion` with the chosen model. Open the hard trace in the Studio: the router span carries the band the request landed in.

### Step 2 · Switch the profile

`orq.smart_routers.update(smart_router_id=..., profile="SMART_ROUTER_PROFILE_QUALITY")` and repeat the two prompts. The key and `model_ref` do not change, so the app does not either.

```text
[2] profile        SMART_ROUTER_PROFILE_QUALITY
    easy -> gpt-4.1-mini                 $0.000425  auto_router=True  trace=d7747eb1d4873fc93b19c507d1fec50b
    hard -> claude-haiku-4-5-20251001    $0.003693  auto_router=True  trace=9d798a113240af756f6677c4a9a74ae9
```

The easy question moved one band up (3.3x the cost for the same one-liner). The hard one stayed on the model the router already trusted.

### Step 3 · Pin traffic with a routing rule

Create `ws-route-mini-to-nano` scoped to your `project_id` with the CEL `metadata["tier"] == "free" && model == "openai/gpt-4o-mini"` and target `openai/gpt-4.1-nano`. Then call with `extra_body={"metadata": {"tier": "free"}}` and read the trace.

```text
[3] project rule   rrl_01m21eyd4z3jb2hez0ejcth1w0 project=01a082d7-b8cc-7c86-bfe8-83f9cb47688b cel=metadata["tier"] == "free" && model == "openai/gpt-4o-mini"
    tier=free call -> gpt-4o-mini                  rule_fired=False  trace=8dd37981e96d16561ce6043c176cd106
    workspace rule rrl_01m21fwmhkw3q9sv0b37wx8gaa ws_module=03  -> gpt-4.1-nano   rule_fired=True  trace=052a64b6c580dc0e17c859d1f50db608
    workspace rule rrl_01m21fwmhkw3q9sv0b37wx8gaa ws_module=no  -> gpt-4o-mini    rule_fired=False  trace=860ad50d66c7139ad8a4d437b8f72dc5
    disabled rrl_01m21eyd4z3jb2hez0ejcth1w0, deleted rrl_01m21fwmhkw3q9sv0b37wx8gaa
```

Two things happened. The project-scoped rule was created and validated, but did not match: in this workspace a plain router call carries no project scope (`project_id` is empty on its trace, with an all-projects key and with a project-scoped key alike), and a project rule only sees requests that have one, such as the agents module 08 runs. So the solution proves the redirect with a workspace-wide rule whose CEL is gated on a metadata key nobody else sends, `metadata["ws_module"] == "03"`, and deletes it afterwards. The proof is in the spans of the matching trace:

```bash
$ orq request GET /v3/traces/052a64b6c580dc0e17c859d1f50db608/spans --json | jq -c '.body.data[] | {type, name, model}'
{"type":"span.load_balancer","name":"load-balancer","model":""}
{"type":"trace","name":"chat.openai","model":"gpt-4.1-nano"}
{"type":"span.chat_completion","name":"chat gpt-4.1-nano","model":"gpt-4.1-nano"}
```

The request asked for `gpt-4o-mini`; a `span.load_balancer` span records the rule's target and `gpt-4.1-nano` answered. The project rule is left in place, disabled, for module 08.

### Step 4 · The same from the CLI

```bash
$ orq smart-routers list --json | jq -c '.data[] | select(.key=="ws-refund-router") | {key, model_ref, profile, models}'
{"key":"ws-refund-router","model_ref":"orq-research@orq/ws-refund-router","profile":"SMART_ROUTER_PROFILE_QUALITY","models":["openai/gpt-4o-mini","openai/gpt-4.1-mini","openai/gpt-4.1","anthropic/claude-haiku-4-5-20251001"]}
$ orq request GET '/v2/routing-rules?project_id=01a082d7-b8cc-7c86-bfe8-83f9cb47688b' --json | jq -c '.body.data[] | {_id, display_name, enabled, cel: .expression.cel, target: .models_config.models[0].model}'
{"_id":"rrl_01m21eyd4z3jb2hez0ejcth1w0","display_name":"ws-route-mini-to-nano","enabled":false,"cel":"metadata[\"tier\"] == \"free\" && model == \"openai/gpt-4o-mini\"","target":"openai/gpt-4.1-nano"}
```

`orq smart-routers create --example` and `orq request POST /v2/routing-rules` take the same bodies the SDK sends.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Create a smart router called `ws-refund-router` with the orq MCP tools or the `orq smart-routers` CLI over `openai/gpt-4o-mini`, `openai/gpt-4.1-mini`, `openai/gpt-4.1` and `anthropic/claude-haiku-4-5-20251001` with the COST profile. Send 5 refund questions of mixed difficulty to its `model_ref`, then use `query_analytics` to compare the cost of those 5 calls against 5 identical calls sent straight to `openai/gpt-4.1`. Report cost per call, which model the router picked for each, and whether COST or QUALITY is the right profile for a refund desk.

## Done when

- [ ] `orq smart-routers list` shows `ws-refund-router` with your pool
- [ ] Two traces with a `span.auto_router` span name different models for the easy and the hard prompt
- [ ] One trace with a `span.load_balancer` span shows `gpt-4.1-nano` answering a request that asked for `gpt-4o-mini`
- [ ] `orq request GET /v2/routing-rules` shows `ws-route-mini-to-nano` with `enabled: false`

## Gotchas

- A Smart Router referenced by an experiment cannot be deleted. Update its pool or profile instead, or create a new key.
- CEL field names are not what you would guess: `metadata["tier"]` works, `metadata.tier` is rejected with `unknown function "tier"`; `identity` is a string, not `identity.id`; headers are `headers["x-tier"]`.
- A project-scoped rule matches only requests that carry a project scope. Raw `/v3/router` calls did not, whatever key signed them. Workspace-wide rules apply to everyone: gate the CEL on a metadata key you own and delete the rule when done.
- New rules and updates take a few seconds to reach the gateway; the solution waits 10 s before calling.
- A matching rule replaces `model`, `load_balancer` and `fallbacks` from the request; it does not merge with them.
- `openai/gpt-4.1-nano` is not in `orq models list` for this workspace yet answers through the gateway; `anthropic/claude-haiku-4-5` shows `enabled: false` while the dated id `anthropic/claude-haiku-4-5-20251001` is enabled. Test a model with `orq chat create` before putting it in a pool.
- Routing rule list items dump as `_id`; create and update responses as `id`.

## New in orq 4.13

The Smart Router got its own page in the AI Gateway: every router, the band each pool model lands in from the intelligence index, and a copyable invocation snippet. `route_pool` picks from N candidates instead of one strong and one cheap model.

## Go further

Combine both: put the `model_ref` of the router in a routing rule's `models_config` so a whole tier of traffic is auto-routed, and keep `fallbacks` from module 01 on the request for the days a provider is down.
