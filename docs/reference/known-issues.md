# Known issues

Dated notes on SDK, CLI and platform behavior the modules work around, and the longer tail of gotchas that did not fit on a module page. Re-check each one on a release refresh; delete it when the platform fixed it. Behavior that is part of the lesson stays on the module page.

## Alerts and webhooks

- 2026-10-29 `orq.telemetry.query` and `orq.alerts.list` raise `ResponseValidationError` in SDK 4.17 (the API echoes `sort: ""`, and an evaluated alert has `severity: ""`). `entities.telemetry_query`, `list_alerts` and `alert_triggers` use REST for those.
- 2026-10-29 SDK 4.14's `webhooks.update` returns 200 and changes nothing (it sends an empty body); `PATCH /v2/webhooks/<id>` over REST works, and `ensure_webhook` uses it to re-point the URL. `webhooks.get` returns `failure_count` as `None`, so a target that stores nothing (httpbin) gives no signal at all.
- 2026-10-29 A new tunnel means a new URL. `make module M=alerts-and-webhooks` re-points `ws-events-webhook` and `ws-alert-notifier` to the current `WS_WEBHOOK_URL`; nothing is recreated.
- 2026-10-29 orq.ai switches a webhook off after 10 failed deliveries (`enabled: false`, `failure_count: 10`); a dead tunnel gets there in minutes and nothing arrives afterwards even once the URL is right. `ensure_webhook` PATCHes `enabled: true` on every run; `orq webhooks list` shows both fields, the SDK's `get` hides `enabled`.
- 2026-10-29 Notifiers and webhooks are different things: a notifier is where alerts and budgets send their notifications; a webhook is a subscription to workspace events. Both can point at the same URL.
- 2026-10-29 `make reset-workspace` deletes the alert, the notifier and the webhook by prefix; the trigger history goes with the alert.

## Annotation queues and automations

- 2026-10-29 `retrieve_item` returns an empty model in SDK 4.17 (no `input` or `output`), and `traces.get_span` in SDK 4.14 drops `output` (not retested). Read the span over REST instead: `/v3/traces/{trace_id}/spans/{span_id}`, `attributes.gen_ai.input.messages[0].parts[0].content` for the question and `attributes.gen_ai.output` for the output items, either a JSON string or `{"_value": [...]}` for an agent whose tools run in orq. The answer is the last `message` item.

## Budgets and keys

- 2026-10-29 SDK 4.14: `mgmt.budgets.list()` fails on an empty list (`data` missing) and `api_keys.create()` rejects the documented `single` scope. The solution uses `httpx` against `/v2/budgets` and `/v2/api-keys`.

## Coding agents

- 2026-10-29 `orq skills` (platform Skill entities) and `orq connect skills` (files for agents) are different nouns.

## Evals and agents in CI

- 2026-10-29 Both gates upload their Experiment runs under `settings.path` (`<ORQ_PROJECT>/workshop`, so `orq-workshop/workshop` by default; `ORQ_PATH` overrides it). `evaluatorq.red_team` has no path parameter, so `redteam_gate.py` patches its upload call; without that patch the run would land in the workspace's Default project and be invisible while `orq-workshop` is the active project. The printed URL always opens the right run.

## Failure analysis, Evaluators and experiments

- 2026-10-29 The SDK's `Attributes` model on search results is empty in SDK 4.17. Read `gen_ai.output`, `metadata.*` and `thread_id` from the raw JSON.

## Guardrails

- 2026-10-29 `orq.guardrail_rules.list()` in SDK 4.14 fails on the `_id` field the API returns. The solution uses `GET /v2/guardrail-rules`. Project rules only appear when you pass `project_id`.
- 2026-10-29 Request-level `guardrails` are ignored on `/v3/router/responses` (accepted, not enforced, no error) as of 4.14.17. Step 3 uses `api="chat"` for that reason; rules apply to both endpoints.
- 2026-10-29 Since orq.ai API 4.14.17, `/v2/guardrail-rules` answers `403 not authorized for this endpoint` to the repo's workspace key (a legacy `workspace_jwt` service-account token). `entities.rules_api` retries the call through `orq request` with the `ORQ_API_KEY` your shell exported before `.env` overrode it, so log in with the CLI (`orq auth login`) and keep that key in the shell. A key minted by `orq setup --local` is a different kind and should not need the fallback; if you get the 403 with one, tell the instructor.

## Knowledge base and RAG

- 2026-10-29 `search_options.include_metadata` shows `metadata.topic` through the CLI and REST; the SDK model drops it (SDK 4.14, not retested).

## Managed agents

- 2026-10-29 Step 5 failed on 2026-10-29 against orq.ai API 4.17.17: the `previous_response_id` follow-up after a turn that used the agent's code tools answered `400 No tool output found for function call`, in three runs. It worked when this module's output was captured.
- 2026-10-29 SDK 4.14 (not retested on 4.17) rejects the built-in tool names the docs use (`orq:datetime`, `orq:web_search`) client-side; it knows `orq:current_date`, `orq:google_search`, `orq:web_scraper`. Either way, attach built-ins to the agent, a request `tools` array is ignored on `agent/` calls.

## MCP servers and gateway

- 2026-10-29 `orq_ai_sdk 4.17` MCP models expect `id` but the API returns `_id`, so `orq.mcp_servers.create(...).mcp_server.id` and every tool `id` after `sync` are `None`. The solution reads the raw records with one `GET /v2/mcp-servers/<id>`. The CLI shows `_id` correctly.

## Troubleshooting with orqi

- 2026-10-29 `.env` overrides the shell by design, which is why Step 2 breaks the client in code rather than through a temp env file.

## Smart routing

- 2026-10-29 Since orq.ai API 4.14.17, `/v2/routing-rules` answers `403 not authorized for this endpoint` to the repo's workspace key (a legacy `workspace_jwt` service-account token). `entities.rules_api` retries the call through `orq request` with the `ORQ_API_KEY` your shell exported before `.env` overrode it, so log in with the CLI (`orq auth login`) and keep that key in the shell. A key minted by `orq setup --local` is a different kind and should not need the fallback; if you get the 403 with one, tell the instructor.
- 2026-10-29 `gpt-5.4-nano` and `gpt-5.6-luna` cost the same; the COST profile still prefers nano for easy questions because the bands rank by intelligence index, not by price alone.
- 2026-10-29 Routing rule list items dump as `_id`; create and update responses as `id`.

## Tracing

- 2026-10-29 `orq.traces.get` and `get_span` return the metadata block empty in SDK 4.17. `orq request GET /v3/traces/<id> -o json | jq .body.trace.attributes.metadata` shows it.
