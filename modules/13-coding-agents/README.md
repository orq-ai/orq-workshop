# 13 · Coding agents

!!! abstract "Your workspace from a coding agent, and the wrap-up"
    The same gateway, MCP server and skills you used from Python all day are one command away from Claude Code, OpenCode, Pi and Codex. A coding-agent session is just another traced, budgeted client of your workspace.

| | |
|---|---|
| **Time** | 25 min |
| **Prerequisites** | module 00; at least one of Claude Code, OpenCode, Pi or Codex installed |
| **You will have** | a dry-run of every file `orq connect` would touch, the exact env `orq launch` injects, the list of skills that ship in the CLI, one coding-agent session visible as traces with its cost, and a checklist to repeat this in your own repo. |

## Why

Every module ends with "With your coding agent". This one explains what that line does. Once you see that a Claude Code turn is four `messages.anthropic` traces sharing a session id, with cache writes as the dominant cost, you understand why budgets (module 05) and identities apply to developers as much as to end users.

## The one concept to understand first

`orq` wires a coding agent along three capabilities and two lifetimes.

![Diagram: how orq wires a coding agent. On your machine, orq launch or orq connect writes gateway, skills and mcp wiring into the coding agent (Claude Code, OpenCode, Codex or Pi) and links the 14 bundled skills into its skills directory; the agent then sends its model calls to the orq AI Gateway, which records them as messages.anthropic traces grouped by session id with cost, and talks to the orq MCP server at /v2/mcp over OAuth.](assets/coding-agent-wiring.png)

| Capability | What it does | Needs a credential |
|---|---|---|
| `gateway` | Writes a provider entry into the agent's own config so its model calls go through `https://my.orq.ai/v3/...` | yes |
| `skills` | Links the orq skills (they ship inside the CLI binary) into the skills directory the agent reads | no |
| `mcp` | Registers `https://my.orq.ai/v2/mcp` as `orq-workspace` in the agent's MCP config; the agent logs in over OAuth | no |

`orq launch <agent>` does all three for one session and leaves nothing on disk. `orq connect [agent...] [capability...]` does it permanently; `--local` writes `mcp` and `skills` into the current project instead of your home directory, `gateway` is machine-wide either way. `orq disconnect` removes exactly what `connect` wrote.

## Steps

`modules/13-coding-agents/run.py` runs every command below with `--dry-run` and redacts the key. `make m13` runs the solution. Nothing in this module writes to `~/.orq`, `~/.claude` or an agent config unless you drop `--dry-run` yourself.

### Step 1 · What is wired, and what `--local` would change

```bash
$ orq connect --status
```

Expected output (this machine):

```text
     AGENT   CAPABILITY  SCOPE   WORKSPACE     LOCATION
  ✓  claude  mcp         global                ~/.claude.json
  ✓          skills      global                ~/.claude/skills
  ✓  codex   gateway             orq-research  ~/.codex/orq.config.toml
  ✓          mcp         global                ~/.codex/config.toml
  ✓  kimi    gateway             orq-research  ~/.kimi-code/config.toml
  ✓          mcp         global                ~/.kimi-code/mcp.json
  ✓  kilo    gateway             orq-research  ~/.config/kilo/kilo.json
  ✓          mcp         global                ~/.config/kilo/kilo.json
  ✓  pi      gateway             orq-research  ~/.pi/agent/models.json
- skills version 415edd5
- detected but not wired: opencode
```

Claude Code has no `gateway` row: it is configured through environment variables, not a config file, so only `launch` can route it. This machine also has `kimi` and `kilo` wired and `opencode` detected but not wired; your list will differ. Now ask what a project-local wiring would touch, one agent at a time:

```bash
$ orq connect claude --local --dry-run
$ orq connect opencode --local --dry-run
$ orq connect pi --local --dry-run
$ orq connect codex --local --dry-run
```

Expected output:

```text
! --local scopes mcp and skills only: gateway is machine-wide either way
- dry run — files that would change, nothing written
- claude   gateway   no gateway provider config for this agent
- claude   mcp       ~/conductor/workspaces/orq-workshop/djibouti/.mcp.json
- claude   skills    ~/conductor/workspaces/orq-workshop/djibouti/.claude/skills

! --local scopes mcp and skills only: gateway is machine-wide either way
- dry run — files that would change, nothing written
- opencode gateway   ~/.config/opencode/opencode.json
- opencode mcp       ~/conductor/workspaces/orq-workshop/djibouti/opencode.json
-          skills    ~/conductor/workspaces/orq-workshop/djibouti/.agents/skills

! --local scopes mcp and skills only: gateway is machine-wide either way
- dry run — files that would change, nothing written
- pi       gateway   ~/.pi/agent/models.json
- pi       mcp       no MCP support in this agent
-          skills    ~/conductor/workspaces/orq-workshop/djibouti/.agents/skills

! --local scopes mcp and skills only: gateway is machine-wide either way
- dry run — files that would change, nothing written
- codex    gateway   ~/.codex/orq.config.toml
- codex    mcp       ~/conductor/workspaces/orq-workshop/djibouti/.codex/config.toml
-          skills    ~/conductor/workspaces/orq-workshop/djibouti/.agents/skills
```

Read the third column: Claude Code reads `.mcp.json` and `.claude/skills`, Codex reads `.codex/config.toml`, OpenCode reads `opencode.json`, and the last three share `.agents/skills`. Pi has no MCP client, so it gets gateway and skills only. Without `--local` the same command writes to `~/.claude.json`, `~/.codex/config.toml`, `~/.agents/skills` and `~/.claude/skills`.

### Step 2 · What `orq launch` injects

```bash
$ orq launch claude --dry-run
```

Expected output:

```text
binary: claude
args:   
env:
  ANTHROPIC_API_KEY=
  ANTHROPIC_AUTH_TOKEN=<redacted>
  ANTHROPIC_BASE_URL=https://my.orq.ai/v3/anthropic
  ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic/claude-haiku-4-5
  ANTHROPIC_DEFAULT_OPUS_MODEL=anthropic/claude-opus-5
  ANTHROPIC_DEFAULT_SONNET_MODEL=anthropic/claude-sonnet-5
  ANTHROPIC_MODEL=anthropic/claude-sonnet-5
  ANTHROPIC_SMALL_FAST_MODEL=anthropic/claude-haiku-4-5
  ORQ_API_KEY=<redacted>
  ORQ_SERVER=https://my.orq.ai
note:   a real run links 14 skills into /Users/arian/conductor/workspaces/orq-workshop/djibouti/.claude/skills for the session and removes them on exit
Note: ORQ_API_KEY may not belong to the workspace 'orq auth login' selected; the key wins. Pass --model against that workspace's catalogue, or re-run 'orq setup' to mint a key for the one you logged into.
```

Four things to notice. `ANTHROPIC_BASE_URL` points at the gateway's Anthropic Messages endpoint, `ANTHROPIC_AUTH_TOKEN` is your orq key, `ANTHROPIC_API_KEY` is set to empty on purpose (a value there makes Claude Code bypass the gateway), and every model id carries the `anthropic/` prefix. MCP is not in the env because Claude Code already has the `orq-workspace` entry from Step 1; for a clean machine `launch` adds it for the session.

```bash
$ orq launch opencode --dry-run
```

```text
binary: opencode
args:   
env:
  OPENCODE_CONFIG_CONTENT={"$schema":"https://opencode.ai/config.json","provider":{"orq":{"npm":"@ai-sdk/openai-compatible","name":"Orq AI Gateway","options":{"apiKey":"<redacted>","baseURL":"https://my.orq.ai/v3/router"},"models":{"alibaba/qwen3.5-27b":{"name":"alibaba/qwen3.5-27b"},"alibaba/qwen3. ... (9409 more chars)
  ORQ_API_KEY=<redacted>
  ORQ_SERVER=https://my.orq.ai
note:   a real run links 14 skills into /Users/arian/conductor/workspaces/orq-workshop/djibouti/.agents/skills for the session and removes them on exit
Note: ORQ_API_KEY may not belong to the workspace 'orq auth login' selected; the key wins. Pass --model against that workspace's catalogue, or re-run 'orq setup' to mint a key for the one you logged into.
```

OpenCode gets its whole provider config through one env var, with the model list pulled from your workspace's enabled catalogue, so its model picker shows exactly what the gateway allows. Codex gets `-c model_provider=orq -c model_providers.orq.base_url=https://my.orq.ai/v3/router -c model_providers.orq.wire_api=responses` on the command line instead.

Either way, every model call the agent makes is a trace with tokens, latency and cost, and Budgets and rate limits apply to it. The docs say so in one line: "Every call is traced with cost, tokens, and latency, and Budgets and rate limits apply" ([CLI reference](https://docs.orq.ai/reference/cli)).

### Step 3 · The skills that ship in the CLI

`orq doctor -o json` reports the skills bundle (`"id": "skills"`, `"version": "415edd51..."`) and `orq connect --status` prints the short form `skills version 415edd5`. The files are materialized under `~/.orq/snapshot/gen-<fingerprint>/` and symlinked into each agent's skills directory; `~/.orq/materialized-skills.json` records every link.

```bash
$ make m13     # step 3 lists them from the snapshot
```

```text
── Step 3 · The skills that ship in the CLI ───────────
snapshot : /Users/arian/.orq/snapshot/gen-2a16641ad77bdb01
    evaluatorq                       Write and run evaluatorq evaluation scripts (Python or TypeScript) for a single agent or d
    orq-analyze-trace-failures       Read production traces, identify what's failing, and build failure taxonomies using open c
    orq-build-agent                  Design, create, and configure orq.ai Agents with tools, instructions, knowledge bases, and
    orq-build-evaluator              Create validated LLM-as-a-Judge evaluators following best practices — binary Pass/Fail jud
    orq-compare-agents               Run cross-framework agent comparisons using evaluatorq from orqkit — compares any combinat
    orq-evaluator-alignment          Align, calibrate, or improve an existing binary Pass/Fail LLM-as-a-judge (orq evaluator) s
    orq-generate-synthetic-dataset   Generate and curate evaluation datasets — structured generation via dimensions-tuples-NL, 
    orq-invoke-deployment            Invoke orq.ai deployments, agents, and models via the Python SDK or HTTP API. Use when a u
    orq-manage-skills                Manage orq.ai Skills (the platform entity, formerly called Snippets) end-to-end — list, ge
    orq-optimize-prompt              Analyze and optimize system prompts using a structured prompting guidelines framework — AI
    orq-red-team                     Invoke the evaluatorq red teaming CLI to run adversarial attacks against deployed agents o
    orq-run-experiment               Create and run orq.ai experiments — compare configurations against datasets using evaluato
    orq-setup-observability          Set up orq.ai observability for LLM applications. Use when setting up tracing, adding the 
    orq-simulate-agent               Run multi-turn agent simulations using evaluatorq's first-class simulation primitives (`si
next     : paste a skill name into your coding agent's prompt, e.g. 'use the orq-setup-observability skill'
```

Fourteen skills, one workflow each. The name links to the `SKILL.md` that the agent reads; the docs catalogue at [Orq Skills](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-skills#skills) has the same list with longer descriptions.

| Skill | Module | What it does |
|---|---|---|
| [`orq-setup-observability`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-setup-observability/SKILL.md) | 00 | instrument an app: gateway proxy or OpenTelemetry, `@traced`, trace enrichment |
| [`orq-analyze-trace-failures`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-analyze-traces/SKILL.md) | 07 | read production traces, build a failure taxonomy (repo name is now `orq-analyze-traces`) |
| [`orq-build-evaluator`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-build-evaluator/SKILL.md) | 07 | create a validated Pass/Fail LLM-as-a-Judge evaluator |
| [`orq-evaluator-alignment`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-evaluator-alignment/SKILL.md) | 07 | align an existing judge to human labels and rewrite its prompt |
| [`orq-build-agent`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-build-agent/SKILL.md) | 08 | design and create an Agent with tools, instructions, knowledge base, memory |
| [`orq-generate-synthetic-dataset`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-generate-synthetic-dataset/SKILL.md) | 09 | generate, expand and clean an evaluation dataset |
| [`orq-run-experiment`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-run-experiment/SKILL.md) | 09 | create and run an Experiment against a dataset with evaluators |
| [`orq-invoke-deployment`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-invoke-deployment/SKILL.md) | 11 | call a deployment, agent or model via SDK or HTTP |
| [`orq-compare-agents`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-compare-agents/SKILL.md) | 11 | compare orq, LangGraph, CrewAI, OpenAI Agents SDK or Vercel agents on one dataset |
| [`evaluatorq`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/evaluatorq/SKILL.md) | 11 | write and run an evaluatorq script with custom scorers |
| [`orq-simulate-agent`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-simulate-agent/SKILL.md) | 11 | multi-turn simulations with `simulate()` and a built-in judge |
| [`orq-red-team`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-red-team/SKILL.md) | 12 | OWASP-ASI and OWASP-LLM attacks through the evaluatorq CLI |
| [`orq-manage-skills`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-manage-skills/SKILL.md) | — | list, create, update, retire platform Skills (the entity, formerly Snippets) |
| [`orq-optimize-prompt`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-improve-agent/SKILL.md) | — | analyze and rewrite a system prompt against a guidelines framework (repo name is now `orq-improve-agent`) |

The docs catalogue adds a fifteenth, [`orq-cli`](https://github.com/orq-ai/assistant-plugins/blob/main/skills/orq-cli/SKILL.md), that the binary does not bundle yet.

The Claude Code slash commands `/orq:quickstart`, `/orq:workspace [section]`, `/orq:traces [--status error] [--last 24h]`, `/orq:models [term]` and `/orq:analytics [--last 24h] [--group-by model]` come from the Claude Code plugin, not from the CLI: `claude plugin marketplace add orq-ai/assistant-plugins` then `claude plugin install orq-skills@orq-claude-plugin`. Use one path or the other for MCP, or you end up with the server registered twice ([Orq Skills](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-skills)).

### Step 4 · The orq MCP server, by hand

`orq connect` and `orq launch` register `https://my.orq.ai/v2/mcp` under the name `orq-workspace`. Any MCP client can do the same:

```bash
$ claude mcp add --transport http orq https://my.orq.ai/v2/mcp                                   # OAuth, sign in on first use
$ claude mcp add --transport http orq https://my.orq.ai/v2/mcp --header "Authorization: Bearer ${ORQ_API_KEY}"
$ codex mcp add orq-workspace --url https://my.orq.ai/v2/mcp --bearer-token-env-var ORQ_API_KEY
```

The documented tool list has 38 tools in 11 categories. Each has a one-line description in the [Available Tools](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-mcp#available-tools) table on docs.orq.ai:

| Category | Tools | What they do |
|---|---|---|
| Agents | `get_agent`, `create_agent`, `update_agent`, `invoke_agent`, `retrieve_agent_response` | read, create and version an Agent; invoke it through the Responses API |
| Analytics | `get_analytics_overview`, `query_analytics` | workspace snapshot; drill-down with filters and grouping |
| Dataset | `create_dataset`, `list_datapoints`, `create_datapoints`, `update_datapoint`, `delete_datapoints`, `delete_dataset` | datasets and their rows, 100 datapoints per call |
| Deployments | `create_deployment`, `get_deployment` | deployments by key |
| Evaluator | `get_llm_eval`, `get_python_eval`, `create_llm_eval`, `create_python_eval`, `update_llm_eval`, `update_python_eval` | LLM-as-a-Judge and Python evaluators |
| Experiment | `list_experiment_runs`, `get_experiment_run`, `create_experiment` | runs, exports (JSON/JSONL/CSV), experiments from a dataset |
| Models | `list_models`, `invoke_model` | the workspace's model catalogue; a direct model call |
| Search | `search_entities`, `search_directories`, `search_docs` | find any entity or directory; query the orq docs |
| Skills | `create_skill`, `update_skill`, `get_skill`, `list_skills`, `delete_skill` | platform Skills, the entity |
| Traces | `list_traces`, `get_span`, `list_spans` | traces by model, type, project, thread, time; spans compact or full |
| Workspace | `delete_entity` | delete any entity by type and id |

The live server exposes a few more (orqi counts 43 after filtering three invocation tools), so treat the docs table as the stable core.

This is Orq's own MCP server, the one coding assistants talk to. It is not the MCP Portal of module 10, where "MCP Server" means a third-party server that orq connects to and re-exposes to Agents and to the MCP Gateway at `/v3/mcp/<key>`.

### Step 5 · A coding session is a set of traces

This workspace already has one: a headless run from module 06, `orq launch claude -- -p "run orq doctor and summarise in three lines"`. Find it by session id:

```bash
$ make m13     # step 4
```

```text
── Step 4 · Coding-agent sessions as traces ───────────
sessions : 0 in the last 24h
next     : open https://my.orq.ai/traces and filter by model anthropic/claude-sonnet-5
```

```bash
$ orq traces query-oql --from 24h --to now --oql 'fetch traces | filter session_id == "45561444-0188-4a37-b50c-483de2e28e6c"' -o json \
    | jq -r '.search.data[] | [.trace_id, .name, .cost.total, .usage.prompt_tokens, .usage.completion_tokens] | @tsv'
```

```text
36e372a44a60f2c4a745c4f4d933b877	messages.anthropic	0.0183379	66169	65
eaa1e73e096dc8913d41486379d8c3fa	messages.anthropic	0.0160852	64234	99
5a6442d80dec93921355ba3024850f70	messages.anthropic	0.108361	43348	7
d2ac649ee129cf82cc08178feff8bfd0	messages.anthropic	0.160754	63258	261
```

Four model calls, one `session_id`, thirty cents, for a prompt that produced three lines of text. Open `d2ac649ee129cf82cc08178feff8bfd0` in the Studio: the span is `span.responses` on route `/v1/messages`, model `anthropic/claude-sonnet-5`, `tools.count` 36, and the cost is almost all `cache_write_cost` (0.158 of 0.161) because the first turn writes the 63k-token system prompt and tool catalogue into the prompt cache. The next turns read it back (`prompt_cached_tokens` 63256 and 64232) and cost a tenth. The `metadata` block carries `x-claude-code-session-id`, `user-agent: claude-cli/2.1.265` and `anthropic-beta`, and `orq.coding_assistant.session_id` is what the Studio groups on.

Codex works the same way by design: it sends a stable session id with each Responses request and the gateway groups the round-trips of one run into a session ([Codex](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/codex), release 4.14). No Codex session was run in this workspace, so that shape is documented, not verified here.

### Step 6 · Apply it to your own repo

1. In your repo: `orq connect --local --dry-run`, read the file list, then `orq connect --local`. Commit `.mcp.json` or `opencode.json` if the team should share the wiring; keep `.claude/skills` and `.agents/skills` out of git (they are symlinks into `~/.orq/snapshot`).
2. Launch the agent and paste the setup-observability prompt: "Use the setup-observability skill on this repo. Detect the framework, prefer the AI Router mode, set `service.name`, and stop after the baseline trace is verified." The skill refuses to add enrichment before a baseline trace exists.
3. A good first trace has a model span with `provider/model`, tokens and cost filled in, a name you would search for (`chat.openai`, not `trace-1`), and the request `route`. If you send identity, thread and metadata (module 02), they show on the same span.
4. After a week of traffic: "Use the analyze-trace-failures skill on the last 7 days of traces for project X" and let it build the failure taxonomy before you write an evaluator (module 07).

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Read AGENTS.md. Run `orq connect --status`. Then use the setup-observability skill on this repo and tell me the three changes you would make, without applying them.

While it thinks, run `make m13` in another terminal: the session you are in should appear as a new session id in step 4.

## Done when

- [ ] `orq connect --status` lists at least one agent, and you can say which file `--local` would write for it
- [ ] `orq launch claude --dry-run` shows `ANTHROPIC_BASE_URL=https://my.orq.ai/v3/anthropic` and an empty `ANTHROPIC_API_KEY`
- [ ] You can name the fourteen bundled skills and the skill you would paste first in a new repo
- [ ] `make m13` step 4 shows one session id with more than one call and a cost
- [ ] You can explain the difference between the orq MCP server and the MCP Gateway of module 10

## Gotchas

- `orq launch` without `ORQ_API_KEY` mints a one-hour token from the login session; it cannot refresh mid-session. Export the key for long sessions.
- With the repo key exported you see `Note: ORQ_API_KEY may not belong to the workspace 'orq auth login' selected; the key wins.` That is the expected message when the CLI login and the project key differ. The key decides where the traces go.
- The `claude` binary is what `orq launch` runs; a shell alias with `--dangerously-skip-permissions` does not apply. For headless runs pass the agent's own flags after `--`, for example `--allowedTools "Bash(orq doctor:*)"`.
- `orq traces search` and `query-oql` need both `--from` and `--to`; relative values (`24h`, `now`) work.
- `orq traces thread <id>` prints `[content unavailable]` for Claude Code turns: the gateway stores the Messages request without the message bodies. Use `list_spans` or the Studio for the content.
- The 401 warning in `orq launch opencode --dry-run` (`Could not fetch enabled models`) means the shell's `ORQ_API_KEY` belongs to another workspace. `launch` falls back to a default model and still runs.
- `orq skills` (platform Skill entities) and `orq connect skills` (files for agents) are different nouns.

## New in orq 4.14

Codex sessions are captured as traces and the Studio's getting-started flow offers a CLI path, so `orq launch codex` and `orq setup` are now the documented way in. The `orq connect --local` project scope and `orq traces query-oql` are CLI 8.x.

## Go further

`ANTHROPIC_CUSTOM_HEADERS=$'X-ORQ-METADATA-REPO: acme-api\nX-ORQ-METADATA-TICKET: PROJ-123'` tags every Claude Code request with metadata, since the agent cannot change the request body. Combine it with a per-identity budget from module 05 and you have a spend cap per developer.

Docs: [orq CLI reference](https://docs.orq.ai/reference/cli), [Claude Code](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/claude-code), [OpenCode](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/opencode), [Codex](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/codex), [Orq MCP server](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-mcp), [Orq Skills](https://docs.orq.ai/docs/ai-studio/integrations/code-assistants/orq-skills), [Anthropic Messages API on the gateway](https://docs.orq.ai/docs/ai-gateway/features/anthropic-messages-api).
