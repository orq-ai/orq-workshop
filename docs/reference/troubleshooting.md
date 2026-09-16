# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `400 invalid model format` | model id without provider | use `provider/model`, e.g. `openai/gpt-5.6-luna` |
| `401 API key is not valid for this workspace` | key from another workspace, often a stale `ORQ_API_KEY` in the shell | the repo `.env` wins; check `orq status` for the active workspace |
| `400` when passing `tools` | GPT-5.x on `/chat/completions` | `/responses` (what the app uses), or `reasoning_effort: "none"` on chat completions |
| `orq launch` sessions fail after an hour | no `ORQ_API_KEY`, one-hour minted token | `source .env` before launching |
| every gateway call blocked with 422 | a workspace-wide PII guardrail rule with the detection service down (fail-closed) | scope rules to a project; `make reset` deletes workshop rules |
| `lookup_order` returns not_found after enabling PII redaction | order ids look like identifiers and get redacted | expected, see module 04; use `entities` to exclude, or redact only output |
| `orq budgets list` returns 403 | project-scoped key | budgets need a Management Key |
| `/v2/routing-rules` or `/v2/guardrail-rules` returns `403 not authorized for this endpoint` | the repo's legacy workspace key cannot reach those endpoints since API 4.14.17 | `orq auth login`; `entities.rules_api` then replays the call through `orq request` with the shell's `ORQ_API_KEY` |
| annotation returns 404 | annotation key does not exist in the workspace | create `rating` and `defects` annotations in the Studio first |
| `analyze-trace-failures` finds too few traces | fewer than ~10 traces | `make traffic` |
| MCP server create rejects the URL | loopback or private host | deploy `app/mcp_server.py` publicly or use a tunnel |
| cannot delete a smart router | referenced by an experiment | delete the experiment first |
| spans missing from short scripts | batch exporter did not flush | call `tracing.flush()` before exit |
| red team says `NO VERDICT`, every attack 401 | stale `ORQ_API_KEY` exported in the shell; `uv run --env-file` does not override it | `unset ORQ_API_KEY` or `set -a; source .env; set +a` |
| MCP server or gateway ids come back `None` from the SDK | SDK 4.14 models read `id`, the API returns `_id` | use `model_dump(by_alias=True)["_id"]` or `orq request GET /v2/mcp-servers` |
| `400 No tool output found for function call` continuing an agent turn | a pending `call_id` got no `function_call_output`: a server-side tool's `function_call` was answered locally, or a target stubbed it away | answer every pending call and skip only those whose `call_id` has an `orq:*` sibling (module 08's loop); one failed trace among healthy ones is a platform hiccup, not your loop |
| `mkdocs build --strict` fails | broken link or missing snippet | links inside module READMEs must be plain text, not relative paths |
