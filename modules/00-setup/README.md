# 00 · Setup

!!! abstract "Factor 11: Trigger from anywhere"
    One credential, three doors: the OpenAI-compatible gateway, the native SDK, and the `orq` CLI that also wires your coding agent. Everything in this workshop goes through the same key.

**Time:** 20 min · **Prereqs:** an orq.ai account, Python 3.11+, [uv](https://docs.astral.sh/uv/), a terminal · **You will have:** a working `.env`, a green `orq doctor`, one traced call in your workspace.

## Why

Every later module asserts its result by looking at a trace. Setup exists so that by the end of it you have seen one.

## The one concept to understand first

[`orq` the CLI](https://docs.orq.ai/reference/cli) is not a wrapper around the API. It is the thing that signs you in, mints the project-scoped key your code uses, and connects the coding agents already on your machine (Claude Code, OpenCode, Pi, Codex, Kimi, Kilo) to the gateway, the orq MCP server and the orq skills. Learn it once, use it in every module.

## Steps

### Step 1 · Install the CLI and sign in

```bash
$ curl -fsSL https://cli.orq.ai/install.sh | sh
$ orq auth login          # browser sign-in
$ orq status
```

Expected output (abridged):

```text
authenticated: true
active_workspace_key: <your-workspace>
active_project_name: <your-project>
cli: 8.0.x
```

### Step 2 · Pick a project and mint a key into this repo

`orq setup --local` creates a project-scoped API key and writes it to `./.env`. Say no to wiring coding agents for now, module 13 does that deliberately.

```bash
$ git clone https://github.com/orq-ai/orq-workshop && cd orq-workshop
$ orq projects create --name orq-workshop      # once per workspace, skip if it exists
$ orq switch                                   # pick orq-workshop as the active project
$ orq setup --local --capability gateway       # writes ORQ_API_KEY to ./.env
$ cp -n .env.example .env.tmp && cat .env.tmp >> .env && rm .env.tmp   # append the remaining settings
```

!!! tip "Already have a key?"
    `cp .env.example .env` and paste your key into `ORQ_API_KEY`. Keep `ORQ_PROJECT=orq-workshop` so every entity lands in one project you can wipe later.

### Step 3 · Install Python deps and run the health checks

```bash
$ make setup
$ make doctor
$ make test
$ make smoke
```

Expected output of `make smoke`:

```text
model      : openai/gpt-4o-mini
tool calls : ['lookup_order', 'get_policy', 'issue_refund']
answer     : Your refund for order ord_a1 has been processed successfully. ...
trace id   : ea9b6f0ee87ed1b287b75be88762f9c7
open       : https://my.orq.ai/traces  (search the trace id)
OK
```

### Step 4 · Look at the trace

Open **Traces** in the Studio, paste the trace id in the search box. You see the last model call of the loop, with cost, tokens and latency, and no instrumentation code in the app. The two earlier calls are their own traces; module 02 nests them under one span.

### Step 5 · Meet the sample app

```text
app/refund_agent/
  tools.py     lookup_order, issue_refund, get_policy   (Factor 4: tools are structured outputs)
  agent.py     run_turn(messages) -> messages           (Factor 12: stateless reducer)
  config.py    every setting comes from .env
app/data/
  orders.json  10 orders, some with traps (over-limit, post-window, refunded, PII in notes)
  kb/*.md      the refund policy, later a knowledge base
```

Read `app/refund_agent/agent.py`. It is 90 lines. It is the whole agent.

## With your coding agent

```bash
$ orq launch claude --dry-run     # shows the env and MCP wiring, changes nothing
$ orq launch claude               # or: orq launch opencode / orq launch pi
```

Paste `agent_prompt.md`:

> Read AGENTS.md and app/refund_agent/agent.py. Run `make smoke`. Explain in five lines what happened, which tool calls the model made, and where the trace id came from.

The agent's own model calls go through the gateway too. Look for them in Traces afterwards.

## Done when

- [ ] `orq doctor` shows every check green
- [ ] `make smoke` prints `OK` and a trace id
- [ ] You found that trace in the Studio
- [ ] You can say what `run_turn` returns

## Gotchas

- Model ids are `provider/model`. `gpt-4o-mini` alone returns `400 invalid model format`.
- The repo `.env` overrides a stale `ORQ_API_KEY` exported in your shell. If `make smoke` says "API key is not valid for this workspace", the key belongs to another workspace.
- `orq launch` without `ORQ_API_KEY` mints a one-hour token that cannot refresh mid-session. `source .env` first for long sessions.

## New in orq 4.14

The Studio onboarding now offers a CLI path. `orq setup` is the same flow the product shows to new users.

## Go further

Docs: [orq CLI reference](https://docs.orq.ai/reference/cli), [OpenAI-compatible API](https://docs.orq.ai/docs/ai-gateway/features/openai-compatible-api), [Traces](https://docs.orq.ai/docs/ai-studio/observability/traces).
