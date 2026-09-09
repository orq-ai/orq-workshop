# Working in this repo with a coding agent

This is a training repo for orq.ai. Participants run it with Claude Code, OpenCode, Pi or Codex launched through `orq launch <agent>`, which routes the agent's own model calls through the orq AI Gateway and wires the orq MCP server plus the orq skills.

## Layout

- `app/refund_agent/` is the sample app. It does not change between modules. Compose it, do not edit it, unless a module says so.
- `modules/NN-name/` is one exercise each: `README.md` (the lesson), `run.py` (starter), `solution/` (finished), `agent_prompt.md` (prompt for a coding agent).
- `docs/` is the MkDocs site. Module pages include `modules/NN-name/README.md` via snippets, so edit the module README, not the docs page.
- `evals/` is the CI regression gate. `slides/` is the live-session deck.

## Conventions

- Every entity this repo creates in orq carries the `WS_PREFIX` key prefix (default `ws-`). `make reset` deletes them by prefix. Keep it that way.
- Model ids are always `provider/model`. The default chat model is a non-reasoning model because reasoning models reject `tools` on `/chat/completions`.
- Credentials live in `.env` only. Never print `ORQ_API_KEY`.
- `make smoke` is the fastest health check. `orq doctor` is the second.
- Use `uv run` for every Python invocation.

## Useful orq skills when working here

`setup-observability`, `analyze-trace-failures`, `build-evaluator`, `run-experiment`, `build-agent`, `red-team`, `simulate-agent`, `orq-cli`.
