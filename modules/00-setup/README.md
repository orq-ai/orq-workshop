# Setup

!!! abstract "One key, three doors"
    One credential, three doors: the OpenAI-compatible gateway, the native SDK, and the `orq` CLI that also wires your coding agent. Everything in this workshop goes through the same key.

| | |
|---|---|
| **Time** | 20 min |
| **Prerequisites** | an orq.ai account, Python 3.11+, [uv](https://docs.astral.sh/uv/), a terminal; Node.js only if you run your own tunnel in modules 09 and 14 (`npx localtunnel`) |
| **You will have** | a working `.env`, a green `orq doctor`, one traced call in your workspace. |

## Why

This workshop drives orq.ai from the terminal. The `orq` CLI is how we do it: it signs you in, manages your authentication key, and wires your coding agent to the same workspace.

## The one concept to understand first

`orq` the CLI is not a wrapper around the API. It is the thing that signs you in, mints the project-scoped key your code uses, and connects the coding agents already on your machine (Claude Code, OpenCode, Pi, Codex, Kimi, Kilo) to the gateway, the orq.ai MCP server and the orq.ai skills. Every entity in the workspace is a subcommand you can script. Learn it once, use it in every module.

It is open source: the binary you install below is built from [orq-ai/orq-cli](https://github.com/orq-ai/orq-cli), and every command is catalogd in the [CLI reference](https://docs.orq.ai/reference/cli).

## Steps

### Step 1 · Install the CLI and sign in

<!-- termynal -->

```console
$ curl -fsSL https://cli.orq.ai/install.sh | sh
---> 100%
$ orq auth login          # browser sign-in
$ orq status
```

Expected output (abridged):

```text
authenticated: true
active_workspace_key: <your-workspace>
active_project_name: <your-project>
```

Two other doors, and one command worth knowing:

```bash
$ npm install -g @orq-ai/cli   # if you would rather have it from npm
$ orq update                   # replace the binary with the latest
$ orq version                  # the CLI version AND the orq API it was built against
```

That second line of `orq version` matters: when a command exists in the docs but not in your binary, the API version it was built against is usually why.

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

### Step 3 · Install the dependencies and run the four health checks

Four commands, in this order. Each one proves one layer works before the next one relies on it: the Python environment, the orq.ai CLI and your login, the sample app's own logic, and finally one real model call through the gateway. When something breaks later in the workshop, this is the ladder you climb back down.

#### 3a · `make setup`: the Python environment

```bash
$ make setup
```

Runs `uv sync --all-groups --extra langgraph`, which creates `.venv/` and installs the pinned dependencies from `uv.lock`: the orq.ai SDK, the OpenAI client, evaluatorq, OpenTelemetry, the LangGraph extra for module 02, plus the test, docs and notebook tool groups. Then it copies `.env.example` to `.env` if you do not have one yet. Nothing talks to orq.ai.

```text
uv sync --all-groups --extra langgraph
Resolved 194 packages in 24ms
Checked 188 packages in 107ms
```

The first run downloads packages and takes a minute; every later run is the two lines above. If it created `.env`, open it and check `ORQ_API_KEY` is filled (step 2 did that with `orq setup --local`).

#### 3b · `make doctor`: the CLI, your login, your wiring

```bash
$ make doctor
```

Runs `orq doctor`, the CLI's self-check. It does not touch this repo: it reads your `orq` session, calls the orq.ai API and inspects the coding agents installed on the machine. The output is YAML: `auth` (who you are, which workspace), `binary` (CLI and API versions), `checks[N]` (one entry per check, each with a `status` of `pass`, `warn`, `info` or `fail` and a message), then `config`, `output` and `runtime`.

```text
orq doctor
auth:
  active_workspace_key: orq-research
  source: session-file
  status: authenticated
  user_email: you@example.com
binary:
  api_version: 4.17.17
  name: orq
  version: 12.7.5
checks[16]:
  -
    id: session_file
    message: Session file loaded
    status: pass
  ...
```

The count and the list depend on the CLI version and on the coding agents installed on your machine. On `orq 12.7.5` (the capture above) the checks are `session_file`, `credential_store`, `bootstrap_token`, one `coding_agent_*` per detected agent (Codex, OpenCode, Kimi, Kilo, Pi, ...), `coding_agents`, `skills`, `mcp`, `credential_permissions`, and the three `*_base_url` reachability checks. Only `fail` matters:

```bash
$ orq doctor | grep -c "status: fail"     # 0 on a healthy machine
$ orq doctor | grep -B3 "status: fail"    # the message of every failing check
```

`warn` and `info` are about agents you have detected but not wired (`orq connect <agent>` fixes them) and do not block the workshop. `auth.status: authenticated` and `gateway_key_exported: pass` are the two that matter today; a `coding_agent_*` failure only matters for the modules that use that agent (06, 13).

#### 3c · `make test`: the sample app, with no network

```bash
$ make test
```

Runs `pytest -q` over `tests/`: the session and build tests plus five unit tests of the three tools the refund agent calls, `lookup_order`, `get_policy`, `issue_refund`, against the in-memory order store. They check that a customer cannot see another customer's order, that an in-window refund goes through exactly once, that the 30-day window and the exception reasons are enforced, that the EUR 500 limit holds and an unknown tool is rejected, and that every policy topic resolves. No model, no orq.ai: this is the business logic every later module leans on, and the reason a refund "outside policy" in module 16 is a prompt problem, not a tool problem.

```text
uv run pytest -q
.....                                                                    [100%]
24 passed in 0.9s
```

#### 3d · `make smoke`: one real turn through the gateway

```bash
$ make smoke
```

Runs [`app/smoke.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/smoke.py): the same `chat()` the whole workshop uses, once, with "Hi, I want a refund for order ord_a1, I changed my mind." The OpenAI client points at `https://my.orq.ai/v3/router` with your key and uses the Responses API, so the call goes through the orq.ai Gateway: the model calls `lookup_order` and `get_policy`, the app executes each tool locally, the in-window order is refunded with `issue_refund` (some runs stop to ask the customer to confirm first, and the refund follows on the next turn), and the gateway returns an `x-orq-trace-id` header on every model call. The script then asserts two things: a trace id came back (the call went through orq.ai, not straight to OpenAI) and `lookup_order` was called (the model used the tools).

```text
── Step 1 · One refund turn through the gateway ───────
model    : openai/gpt-6-luna
question : Hi, I want a refund for order ord_a1, I changed my mind.
answer   : Your refund of €24.99 has been issued to the original payment method. It should arrive within 5–7 bu…
tools    : lookup_order → get_policy → issue_refund
trace    : 2e3d6942bbbbd4d48e95f8bcf600b4ad
verdict  : OK, the call went through orq and the model called lookup_order
next     : search the trace id in https://my.orq.ai/traces; expect the last model call with cost, tokens and latency
```

If the verdict reads `OK`, everything the workshop needs is in place: environment, credentials, app, gateway. Common failures and what they mean:

| Symptom | Cause | Fix |
|---|---|---|
| `ORQ_API_KEY is empty` | `.env` not filled | `orq setup --local --capability gateway`, or paste a key from **Settings > API keys** |
| `401` from the router | wrong or stale key in `.env` | `.env` beats your shell: check that file, not `echo $ORQ_API_KEY` |
| `404 Model ... not found` | `MODEL` in `.env` is not enabled in the workspace | enable it under **Models**, or set `MODEL=openai/gpt-6-luna` |
| `no x-orq-trace-id header` | `ORQ_BASE_URL` does not point at orq.ai | `ORQ_BASE_URL=https://my.orq.ai` in `.env` (module 06 plants this failure on purpose) |
| `400 ... reasoning_effort` on a tools call | a GPT-5.x model on `/chat/completions` | the app uses `/responses`; on chat completions set `reasoning_effort: "none"` |

#### 3e · `make seed`: every entity the modules expect

```bash
$ make seed
```

Runs `app/refund_agent/entities.py seed`: the dataset, the knowledge base, the two evaluators, the tools, the three managed agents, the alert, the annotation queue and the review dataset, every one with your seat prefix (`WS_PREFIX`, e.g. `ws07`; the examples in these modules write `ws-`, read it as your prefix). It is idempotent: an entity that already exists is found by key and left alone, so run it as often as you like. Seven modules list `make seed` as a prerequisite and module 12's gates need the seeded agent and judge; run it once here and you can start any module. `make reset` deletes everything with the prefix, and refuses the bare shared `ws`.

```text
uv run python -m app.refund_agent.entities seed
── Seed · create every workshop entity ────────────────
dataset  : 01M2... (ws-refund-eval)
kb       : 01M2... (ws-refund-policy)
guard    : 01M2... (ws-refund-limit-guard)
judge    : 01M2... (ws-refund-policy-judge)
tools    : ws-lookup_order, ws-issue_refund, ws-get_policy (code tools: orq runs them)
agent    : ws-refund-agent
...
```

### Step 4 · Look at the trace

Open **Traces** in the Studio, paste the trace id in the search box. You see the last model call of the loop, with cost, tokens and latency, and no instrumentation code in the app. The earlier calls are their own traces; module 02 nests them under one span.

### Step 5 · Meet the sample app

```text
app/refund_agent/
  tools.py     lookup_order, issue_refund, get_policy   (the model emits JSON, this file runs it)
  agent.py     run_turn(messages) -> messages           (no hidden state: items in, items out)
  config.py    every setting comes from .env
app/data/
  orders.json  10 orders, some with traps (over-limit, post-window, refunded, PII in notes)
  kb/*.md      the refund policy, later a knowledge base
```

Read [`app/refund_agent/agent.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/refund_agent/agent.py). It is 90 lines. It is the whole agent.

### Optional · Chat with it in a browser

```bash
$ make chat        # http://127.0.0.1:8002
```

[`app/web.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/web.py) puts the same `chat()` behind `POST /api/chat`; [`web/index.html`](https://github.com/orq-ai/orq-workshop/blob/main/web/index.html) is the page. Transcript, tool chips, model per turn and a **trace** link per answer. [All its features](https://github.com/orq-ai/orq-workshop/blob/main/web/README.md).

## With your coding agent

```bash
$ orq launch claude --dry-run     # shows the env and MCP wiring, changes nothing
$ orq launch claude               # or: orq launch opencode / orq launch pi
```

Paste `agent_prompt.md`:

<blockquote class="agent-prompt-frame" markdown>
Read AGENTS.md and app/refund_agent/agent.py. Run `make smoke`. Explain in five lines what happened, which tool calls the model made, and where the trace id came from.
</blockquote>

The agent's own model calls go through the gateway too. Look for them in Traces afterwards.

## Done when

- [ ] `orq doctor` shows every check green
- [ ] `make smoke` prints `OK` and a trace id
- [ ] You found that trace in the Studio
- [ ] You can say what `run_turn` returns

## Gotchas

- Model ids are `provider/model`. `gpt-6-luna` alone returns `400 invalid model format`.
- The repo `.env` overrides a stale `ORQ_API_KEY` exported in your shell. If `make smoke` says "API key is not valid for this workspace", the key belongs to another workspace.
- `orq launch` without `ORQ_API_KEY` mints a one-hour token that cannot refresh mid-session. `source .env` first for long sessions.

## New in orq.ai 4.15 and 4.17

The orq.ai CLI installs with one command and `orq setup` signs in and wires every coding agent it detects; `orq launch <agent>` runs one through the gateway without writing config ([release 4.15](https://docs.orq.ai/changelog/release-4-15)). Studio opens every page as a tab and lets you hide and reorder sidebar sections, so the sidebar in the screenshots can differ from yours ([release 4.17](https://docs.orq.ai/changelog/release-4-17)).

## Go further

## Official docs

- [orq.ai CLI reference](https://docs.orq.ai/reference/cli)
- [OpenAI-compatible API](https://docs.orq.ai/ai-gateway/features/openai-compatible-api)
- [Traces](https://docs.orq.ai/ai-studio/observability/traces)
