# Working in this repo with a coding agent

This is a training repo for orq.ai. Participants run it with Claude Code, OpenCode, Pi or Codex launched through `orq launch <agent>`, which routes the agent's own model calls through the orq.ai AI Gateway and wires the orq MCP server plus the orq skills.

## Layout

- `app/refund_agent/` is the sample app. It does not change between modules. Compose it, do not edit it, unless a module says so.
- `modules/NN-name/` is one exercise each: `README.md` (the lesson), `run.py` (starter), `solution/` (finished), `agent_prompt.md` (prompt for a coding agent), optional `assets/` (a diagram as `.svg` source plus the exported `.png` the README embeds). Where `solution/run.py` is written in Jupytext percent format (`# %%` cells, top-level code, no `__main__`), `make notebooks` generates a gitignored `notebook.ipynb` next to it; keep new step code top-level and put the explanation in `# %% [markdown]` cells so script and notebook stay one source.
- `docs/` is the MkDocs site. Module pages include `modules/NN-name/README.md` via snippets, so edit the module README, not the docs page. A diagram is an SVG source `modules/NN-name/assets/<slug>.svg` (or `docs/assets/diagrams/`), styled only by classes from `scripts/diagram.css` via `@import url("../../../scripts/diagram.css")`, with `<title>`/`<desc>` and `role="img"`; no inline colors or fonts. Run `make diagrams` to export the committed PNG next to it, view it, and embed `![Diagram: ...](assets/<slug>.png)`; `scripts/mkdocs_hooks.py` serves those files on the site.
- `evals/` is the CI regression gate. `slides/` is the live-session deck.
- App file map: `app/refund_agent/entities.py` seeds, versions and resets the orq.ai entities; `client.py` is the one call to the agent; `tools.py` holds the tool rules that `make seed-workspace` turns into orq.ai code tools; `config.py` reads `.env`. `app/web.py` + `web/index.html` is the chat UI (`make agent-chat-ui`). `app/gateway_check.py`, `app/traffic.py`, `app/insurance.py`, `app/edge.py` and `app/mcp_server.py` back the matching make targets.

## Conventions

- Every entity this repo creates in orq carries the `WS_PREFIX` key prefix (default `ws-`). `make reset-workspace` deletes them by prefix. Keep it that way.
- Model ids are always `provider/model`. The sample app talks to the gateway through the **Responses API** (`/v3/router/responses`), stateless: the full item list every round, `store: false`. GPT-5.x models reject `tools` on `/chat/completions` unless `reasoning_effort` is `"none"`; the LangGraph stretch (chat completions via `ChatOpenAI`) sets it. Every model comes from `.env` (defaults in `.env.example`: `gpt-6-luna` for agent and judge); never hard-code one in a module. Appendix modules still name `gpt-5.6-terra` mid, `gpt-5.6-sol` strong, `gpt-5.4-nano` cheap.
- Credentials live in `.env` only. Never print `ORQ_API_KEY`.
- `make gateway-check` is the fastest health check. `orq doctor` is the second.
- Use `uv run` for every Python invocation. `make test` runs without network.

## Writing

- Name the platform "orq.ai" in prose. Plain `orq` is only for the CLI, identifiers and URLs.
- No em dashes. American English ("summarize", not "summarise").
- Module titles and link text carry no numbers; numbers stay in folder names and URLs.
- No day or hour framing ("Day 1", clock times). Sessions are described in minutes.
- Module READMEs are included into the docs via snippets, so links inside them are absolute URLs (relative links break the build).
- Lesson pages before the simulation must not name the behaviors the simulation is meant to find.

## Useful orq skills when working here

`setup-observability`, `analyze-trace-failures`, `build-evaluator`, `run-experiment`, `build-agent`, `red-team`, `simulate-agent`, `orq-cli`.
