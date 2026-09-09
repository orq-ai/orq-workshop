---
marp: true
theme: orq
paginate: true
footer: "orq.ai workshop · github.com/orq-ai/orq-workshop"
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Building with orq.ai

## A hands-on workshop

**Gateway · Guardrails · Tracing · Evals · Agents · RAG · MCP · Simulation · Red teaming · Coding agents**

3 hours · one refund agent · your priorities decide the order

<!--
Timing: 0:00. Welcome, names, one line each on what they build. This deck is a spine, not a script.
Everything shown lives in the repo. Every block ends with "you try" and a "Done when".
-->

---

## How today works

- **One sample app**, a customer-support refund agent. It grows block by block.
- **Two tracks**, always: by hand (SDK, CLI, Studio) and with your coding agent (`orq launch claude`).
- **You choose the order.** In ten minutes we vote on the blocks. We do four or five of ten.
- **Every block ends with "Done when."** Verify it in the Studio before we move on.
- **Parking lot** on the wall. Anything we skip becomes a follow-up.

<span class="tag">repo</span> `github.com/orq-ai/orq-workshop` · <span class="tag">docs</span> `orq-ai.github.io/orq-workshop`

<!-- 0:03. Point at the parking lot. Ask everyone to have the repo cloned and `make smoke` green before the vote. -->

---

<!-- _class: input -->

## How do you use orq today?

Pre-filled from your survey. Correct it, add to it.

| Question | Your answers | Add live |
|---|---|---|
| How does the team use orq? | Python SDK · AI Studio · gateway as a proxy | |
| Which coding agents? | OpenCode · Claude Code · Pi | |
| Frameworks on top? | LangGraph · orq SDK · Strands | |
| Most used areas | routing · budgets & keys · deployments & agents · tracing · experiments | |
| What you want from today | guardrails & PII · tracing & failure analysis · simulation & red teaming | |

<!-- 0:05. Five minutes. Write their additions on the slide (or the whiteboard). These feed the vote. -->

---

<!-- _class: lead -->

# The map

<!-- 0:12. Fifteen minutes on the map, then vote. -->

---

## orq in one picture

```
 your app / framework / coding agent
            │  OpenAI-compatible request (+ extra_body)
            ▼
 ┌───────────────── AI Gateway ─────────────────┐
 │ routing rules · smart router · fallbacks     │
 │ cache · budgets · guardrails · PII redaction │
 │ MCP Portal: MCP Servers + MCP Gateway        │
 └──────────────┬────────────────────────────────┘
                ▼
 ┌────────────── AI Studio ─────────────────────┐
 │ Traces & threads · Annotations · Evaluators  │
 │ Datasets · Experiments · Agents · Knowledge  │
 │ Memory stores · Prompts · Skills             │
 └───────────────────────────────────────────────┘
      ▲ orq CLI · orq MCP server · orq skills · orqi · evaluatorq
```

<!-- One credential, three doors: gateway, native SDK, CLI. Everything on the left is a request field. Everything on the right is a trace. -->

---

## The refund agent

Three tools. One loop. Ninety lines.

```python
def run_turn(messages, *, extra_body=None, ...) -> TurnResult:   # stateless reducer
    for _ in range(max_tool_rounds + 1):                          # our control flow
        completion = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SCHEMAS,   # NL -> tool calls
            extra_body=extra_body or {})                          # gateway features ride here
        for call in choice.tool_calls:
            result = dispatch(store, call.function.name, args)    # tools are structured outputs
            messages.append({"role": "tool", "content": json.dumps(result)})
```

`lookup_order` · `issue_refund` · `get_policy` — with traps: post-window orders, an already refunded one, a EUR 620 one, PII in a customer note.

<!-- The app never changes across blocks. The request, the workspace and the harness around it do. -->

---

## The spine: 12-Factor Agents

| Factor | Where you will see it today |
|---|---|
| 1 NL to tool calls · 4 tools are structured outputs | gateway call, managed agent `function_call` items, MCP Gateway exposure |
| 2 own your prompts · 3 own your context window | instructions as files, experiments, KB `top_k` and rerank, traces show the context |
| 5 unify execution and business state | identity + thread on every call, memory `entity_id` |
| 6 launch/pause/resume · 11 trigger from anywhere | `previous_response_id`, headless `orq launch -p`, CI cron, coding agents |
| 7 contact humans with tool calls | guardrail 422 as escalation, `tool_approval_required`, annotation queues |
| 8 own your control flow · 9 compact errors | the loop, routing and guardrail rules, short tool errors, fallbacks |
| 10 small focused agents · 12 stateless reducer | advisor/sidekick, gateway subsets, `run_turn`, evaluatorq jobs, replay |

<span class="small">humanlayer/12-factor-agents · full map in the docs</span>

<!-- Do not read the table. Say: every block names its factor. That is how the workshop transfers to your own code. -->

---

## What's new (4.10 to 4.14, CLI 8.x)

- **MCP Portal + MCP Gateway** (4.14): one governed endpoint for many MCP servers, per-tool exposure, denied calls logged
- **Smart Router** page, `route_pool`, quality / balanced / cost profiles (4.13)
- **Advisor and Sidekick** tools on agents (4.13)
- **System guardrails** PII + Secret detection, fail-closed, sampling (4.12, 4.13)
- **Budgets** as an entity: identity, key, project, model scopes; RPM, cost, tokens (4.11)
- **PII redaction plugin** with restore on the way back (4.11)
- **Annotations** with queues and API; guardrail indicators on spans; Codex sessions as traces
- **orq CLI 8**: `orq launch`, `orq connect --local`, `orq traces thread`, `orq doctor`, `orq orqi`
- **evaluatorq**: agent simulation, OWASP red teaming, exit-code gates

<!-- 0:22. One minute. Point at docs/whats-new.md for the module mapping. -->

---

<!-- _class: vote -->

## Vote: pick four or five blocks

Three dots each. Put them on the wall or say them out loud.

| | Block | Minutes | Repo modules |
|---|---|---|---|
| A | Gateway, smart routing, budgets | 25 | 01, 03, 05 |
| B | Guardrails and PII | 25 | 04 |
| C | Tracing and troubleshooting with orqi | 25 | 02, 06 |
| D | Failure analysis to evaluators to experiments | 30 | 07 |
| E | Managed agents | 30 | 08 |
| F | Knowledge base and RAG | 25 | 09 |
| G | MCP servers and the MCP Gateway | 25 | 10 |
| H | Simulation and red teaming | 30 | 11 |
| I | Evals and headless agents in CI | 25 | 12 |
| J | Coding agents wired to orq | 20 | 13 |

<!-- 0:27. Five minutes. Then reorder the rest of the deck on the fly: jump to the block sections by page. Facilitator notes have the vote-to-order table. Suggested default if the vote ties: C, B, D, H, J. -->

---

<!-- _class: lead -->

# Block A · Gateway, smart routing, budgets

<span class="tag orange">modules 01 · 03 · 05</span> Factor 1, 8, 5

---

<!-- _class: block -->

## A · The concept

**Everything is a request field.** Point any OpenAI client at `https://my.orq.ai/v3/router` and add to `extra_body`:

```python
extra_body={
  "timeout":   {"call_timeout": 900},
  "fallbacks": [{"model": "openai/gpt-4.1-nano"}],
  "retry":     {"count": 1, "on_codes": [429, 500, 502, 503, 504]},
  "cache":     {"type": "exact_match", "ttl": 600},
  "load_balancer": {"type": "weight_based", "models": [...]},
  "identity": {"id": "customer-42"}, "thread": {"id": "conv-1"}, "metadata": {"tier": "free"},
}
```

A **smart router** is a model id (`<workspace>@orq/refund-router`) that picks from a pool per request. A **routing rule** rewrites the model for matching traffic at the gateway. A **budget** stops traffic per identity, key, project or model.

---

<!-- _class: block -->

## A · Live demo

```bash
$ make m01        # plain, forced fallback (timeout), cache hit, load balancer
$ make m03        # smart router COST vs QUALITY, one routing rule
$ orq budgets list --profile management   # third call in a minute rejected
```

Watch for: `span.fallback_selected` · cached span with zero cost · `orq.auto_router.selected_model` · the budget error text.

<!-- Have the trace list open before you start. Fallback shows only if gpt-4.1 exceeds 900 ms; rerun if it did not. -->

---

<!-- _class: block -->

## A · You try · Done when

Open `modules/01-gateway/run.py`, fill the three `TODO`s, run it.

- [ ] A trace with a `span.fallback_selected` span
- [ ] A second identical request served from cache
- [ ] Smart router traces show two different selected models across profiles
- [ ] You can say why an unknown model id does not fall back

**Gotchas:** every fallback gets the same timeout · reasoning models reject `tools` on chat completions · budgets need a Management Key.

**Ask your agent:** "Add a fallback chain and a cache to module 01 without touching app/, then fetch the fallback trace's spans over MCP and tell me which model answered."

---

<!-- _class: lead -->

# Block B · Guardrails and PII

<span class="tag orange">module 04</span> Factor 7

---

<!-- _class: block -->

## B · The concept

Three different things, often confused:

| | What it does | Where |
|---|---|---|
| **PII redaction plugin** | replaces PII with placeholders before the provider, restores after | `plugins: [{"id": "pii_redaction"}]` or workspace-wide |
| **System guardrails** | PII Detection, Secret Detection: block, fail-closed | guardrail rule |
| **Your guardrails** | LLM judge or Python function with a pass condition, blocks with 422 | `guardrails: [{"id": ..., "execute_on": "output"}]` or rule |

A blocked request is the **hand-off to a human**. Factor 7 without a framework.

---

<!-- _class: block -->

## B · Live demo

```bash
$ orq pii redact --text "contact me at jane.doe@example.com or +31 6 1234 5678"
$ make m04        # plugin on a refund call, the order-id surprise, a 422 on a EUR 620 refund, a project-scoped rule
```

Watch for: placeholders in the span input, originals in the answer · what happened to `ord_a1` · the 422 body · the guardrail indicator on the span (4.14).

<!-- The order-id redaction is a seeded failure. Let them find it. Then discuss entity lists and output-only guardrails. -->

---

<!-- _class: block -->

## B · You try · Done when

- [ ] A trace where the provider saw `<EMAIL_ADDRESS>` and the customer saw the real address
- [ ] A refund above EUR 500 blocked with 422 by `ws-refund-limit-guard`
- [ ] A guardrail rule scoped to the project, then disabled

**Gotchas:** system guardrails always fail closed · a rule without a project and with an empty expression is workspace-wide · redaction is a design decision per entity type.

**Ask your agent:** "Add a Python guardrail that blocks any answer repeating an email address and attach it to the refund agent's output via the orq MCP tools."

---

<!-- _class: lead -->

# Block C · Tracing and troubleshooting with orqi

<span class="tag orange">modules 02 · 06</span> Factor 3, 5, 11

---

<!-- _class: block -->

## C · The concept

**Level 1**: zero code. Every gateway call is a trace with cost, tokens, latency.
**Level 2**: identity, thread, metadata on the request (top-level fields). Traces become conversations and customers.
**Level 3**: your own spans. `@traced(type="agent")` around the turn, `@traced(type="tool")` around each tool, or OpenTelemetry from any framework (LangGraph, Strands, CrewAI, ...).

Then: **orqi**, the terminal helper. It reads your traces with the orq MCP tools and its own skills: `investigate-root-cause`, `debug-conversation`, `workspace-health-check`, `optimize-cost`.

```bash
$ orqi "list the traces with errors from the last 2 hours and group them by root cause"
```

---

<!-- _class: block -->

## C · Live demo

```bash
$ make m02                          # identity + thread, otel spans, one annotation
$ orq traces thread <trace_id>      # readable transcript
$ orqi /doctor
$ orqi "why did trace <id> fail?"
```

Watch for: the thread view grouping two turns · agent → tool → llm nesting · orqi naming the root cause you already know.

<!-- Seeded failure: a broken ORQ_BASE_URL in a temp .env. orqi has to find a client-side cause, not only a trace. -->

---

<!-- _class: block -->

## C · You try · Done when

- [ ] A trace with a root `agent` span, nested `tool` spans and the LLM spans
- [ ] Two turns grouped under one thread with an identity
- [ ] One annotation on a span
- [ ] orqi found the broken base URL from the error text

**Gotchas:** short scripts must flush the exporter · annotation keys must exist in the workspace · orqi is alpha, pin `ORQI_VERSION`.

**Ask your agent:** "Use the setup-observability skill on this repo and tell me the three changes you would make, without applying them."

---

<!-- _class: lead -->

# Block D · Failure analysis to evaluators to experiments

<span class="tag orange">module 07</span> Factor 2, 9

---

<!-- _class: block -->

## D · The concept

The loop that makes quality measurable:

1. **Look at traces** (twenty is enough). Name what goes wrong: open coding, then axial coding. A **failure taxonomy** of two to four modes.
2. **One evaluator per failure mode.** Binary pass/fail judges, validated against a few labelled examples. Python where a regex will do.
3. **A dataset** of the cases that matter. Real ones first, synthetic to fill gaps.
4. **An experiment**: two configurations, same dataset, same evaluators. Read the table, not the vibes.

The orq skills encode exactly this: `analyze-trace-failures` → `build-evaluator` → `generate-synthetic-dataset` → `run-experiment`.

---

<!-- _class: block -->

## D · Live demo

```bash
$ make traffic    # 20 conversations, half with the vulnerable instructions
$ make m07        # taxonomy from real traces, judge invoked, evaluatorq experiment fixed vs vulnerable
```

Watch for: which failure modes the vulnerable variant produces · the judge's true/false on a good and a bad answer · the experiment URL and the table in the Studio.

<!-- If the room has a coding agent ready, run the skill chain in parallel on a second screen. -->

---

<!-- _class: block -->

## D · You try · Done when

- [ ] A failure taxonomy with at least two named modes from your own traces
- [ ] The LLM judge returns true on a good answer and false on a bad one
- [ ] An Experiment run in the Studio comparing fixed vs vulnerable with two evaluators

**Gotchas:** judges are non-deterministic, gate on means · use a non-reasoning judge model · ten traces is the minimum for a taxonomy.

**Ask your agent:** "Use analyze-trace-failures on traces tagged traffic, then build-evaluator for the top failure mode, then run-experiment on dataset ws-refund-eval."

---

<!-- _class: lead -->

# Block E · Managed agents

<span class="tag orange">module 08</span> Factor 4, 6, 10

---

<!-- _class: block -->

## E · The concept

Same refund agent, hosted by orq: instructions, model, tools (function, HTTP, built-in, MCP), knowledge bases, memory stores, versions, environments.

```python
orq.responses.create(model="agent/ws-refund-agent", input="Refund ord_a2 please",
                     memory={"entity_id": "customer-user_001"}, thread={"id": "conv-7"})
```

Function tools come back as `function_call` items. **Your code executes them** and continues with `previous_response_id`. Tools stay structured outputs; state stays yours.

**Advisor** asks a second model for guidance mid-turn. **Sidekick** delegates a discrete task. Small agents, composed.

---

<!-- _class: block -->

## E · Live demo

```bash
$ orq agents get ws-refund-agent
$ make m08        # invoke with tool dispatch, stream, memory recall, a version bump
$ orq traces thread <trace_id>
```

Watch for: the `function_call` item and the continuation · memory recalling the customer's name on the second call · `@production` in the model reference.

<!-- GET returns tools as action_type with ids. Never PATCH a GET body back. Say it out loud, it saves an hour. -->

---

<!-- _class: block -->

## E · You try · Done when

- [ ] `orq responses create --model agent/ws-refund-agent --input "refund ord_a1"` produces a trace with a tool call and a final message
- [ ] A second call with the same `memory.entity_id` recalls the name
- [ ] A new version exists and can be invoked by reference

**Gotchas:** memory is not automatic, instructions must say what to write · `max_execution_time` counts model time only · legacy `/v2/agents/run` is deprecated.

**Ask your agent:** "Use build-agent to create ws-refund-agent-v2 with the same tools plus an escalate_to_human tool, then invoke it with 'refund ord_a6' and show me the trace."

---

<!-- _class: lead -->

# Block F · Knowledge base and RAG

<span class="tag orange">module 09</span> Factor 3, 13

---

<!-- _class: block -->

## F · The concept

**Chunking is the biggest lever.** `POST /v2/chunking` with `token`, `sentence`, `recursive`, `semantic`, `agentic` strategies, then push the chunks with metadata.

**Search is a request**: `hybrid_search` (vector + keyword), a threshold, `top_k`, a rerank model, optional agentic RAG (query rewrite + document grading).

Three places retrieval can happen:
- your tool (`get_policy` calls `knowledge.search`)
- the gateway, on a plain chat call (`orq.knowledge_bases` in the request): pre-fetched context, no tool call
- the managed agent (`query_knowledge_base` built-in)

**External knowledge base**: your own `/search` endpoint behind the same contract.

---

<!-- _class: block -->

## F · Live demo

```bash
$ orq knowledge-bases search <id> --query "opened electronics after 20 days"
$ make m09        # vector vs keyword vs hybrid vs rerank, chunking strategies, KB as get_policy, gateway-side retrieval
```

Watch for: scores side by side · the retrieval span in the trace · the grounded answer with no tool call.

<!-- Processing is async. `retrieve_processing_status` before searching a fresh datasource. -->

---

<!-- _class: block -->

## F · You try · Done when

- [ ] A policy edge case answered with a retrieved chunk visible as a span
- [ ] `knowledge-bases search` returns that chunk with a rerank score
- [ ] One chunking strategy compared against another on the same document

**Gotchas:** external KB URLs must be public · `top_k` and threshold are the context window, own them · metadata filters need metadata at ingest.

**Ask your agent:** "Add app/data/kb/warranty.md as a new datasource to ws-refund-policy, wait for processing, then search for 'warranty length'."

---

<!-- _class: lead -->

# Block G · MCP servers and the MCP Gateway

<span class="tag orange">module 10</span> Factor 4, 10

---

<!-- _class: block -->

## G · The concept

Three things named MCP:

| | Who connects | What for |
|---|---|---|
| **Orq MCP server** `/v2/mcp` | your coding agent | administer the workspace: agents, datasets, evals, traces, docs |
| **MCP Servers** (MCP Portal) | orq | upstream tool servers you register: URL, auth, discovered tools |
| **MCP Gateway** `/v3/mcp/<key>` | any client, any agent | one endpoint over many servers, expose all/selected/none per server, read-only filters, every call logged, denied calls too |

The gateway is where "small, focused agents" becomes a setting: the refund agent sees `lookup_order` and `get_policy`, never `issue_refund`.

---

<!-- _class: block -->

## G · Live demo

```bash
$ make mcp-server                    # app/mcp_server.py on :8000 (deployed publicly for the portal)
$ make m10                           # register server, sync, gateway with two exposed tools, call through it
$ orq mcp-gateways list-tools ws-refund-gateway
```

Watch for: the discovered tool list after sync · only two tools on the gateway · the call log with exposed vs upstream names.

<!-- Upstream URLs must be public. The instructor deploys app/mcp_server.py before the session; MCP_SERVER_URL in .env. -->

---

<!-- _class: block -->

## G · You try · Done when

- [ ] `list-tools` on the gateway shows exactly the two exposed tools
- [ ] A tool call through `/v3/mcp/<key>` appears in the gateway log
- [ ] You can explain Code Mode vs Direct Mode in one sentence each

**Gotchas:** loopback and private hosts are rejected · tool ids change on upstream rename after re-sync · the MCP Tool type on agents is retired, use the portal.

**Ask your agent:** "Connect ws-refund-gateway to this session, use lookup_order on ord_a2, then tell me which tools the gateway hides from you and why that is the point."

---

<!-- _class: lead -->

# Block H · Simulation and red teaming

<span class="tag orange">module 11</span> Factor 12, 10

---

<!-- _class: block -->

## H · The concept

**Simulation**: a user-simulator LLM plays a persona with a goal against your agent, turn by turn; a judge scores goal reached and rules broken. `simulate()`, `generate_and_simulate()`, replay a previous run to prove a fix.

**Red teaming**: OWASP LLM Top 10 and Agentic (ASI) categories. Static mode replays a fixed attack set (deterministic, CI-safe); dynamic mode adapts mid-conversation. Agent-aware: it reads the agent's tools and memory and attacks what the agent can actually do.

Both push results to the Studio as **Experiment runs**. Both route their attacker and judge calls through the gateway, so they are traced and budgeted like everything else.

---

<!-- _class: block -->

## H · Live demo

```bash
$ make m11        # 2 personas x 2 scenarios, generated personas, red team vulnerable vs fixed (static)
$ uv run eq redteam run -t "agent:ws-refund-agent-vulnerable" --mode static --max-static-datapoints 4 -y
```

Watch for: the resistance rate per target · which attack got a refund on the vulnerable agent · the five-line diff between the two instruction files.

<!-- Keep the datapoint cap small. Dynamic mode is a demo, not a lab. -->

---

<!-- _class: block -->

## H · You try · Done when

- [ ] A simulation run with per-conversation verdicts in the Studio
- [ ] The vulnerable agent fails and the fixed agent passes the same static attack set
- [ ] You can name the OWASP category of the attack that worked

**Gotchas:** simulation is Python only · agents whose tools run in your code need an AgentTarget adapter · attacker and judge cost money, cap them.

**Ask your agent:** "Use red-team on ws-refund-agent-vulnerable for LLM07 and ASI01, then propose the instruction change."

---

<!-- _class: lead -->

# Block I · Evals and headless agents in CI

<span class="tag orange">module 12</span> Factor 6, 11

---

<!-- _class: block -->

## I · The concept

**Evals as regression, not benchmark.** evaluatorq scorers return `pass_`; any failure exits 1; thresholds are means over the dataset. The red-team static gate is the same idea for security.

```yaml
# .github/workflows/evals.yml
jobs:
  quality:  run: uv run python -m evals.regression      # exit 1 on regression
  security: run: uv run python -m evals.redteam_gate     # exit 1 on a successful attack
```

**Headless agents as routine tasks.** `orqi "<prompt>"` and `orq launch claude -p "<prompt>"` run once and exit. Put them on a cron: nightly trace triage, weekly cost report, PR-time failure analysis. One `ORQ_API_KEY`, no vendor keys, a budget on that key.

---

<!-- _class: block -->

## I · Live demo

```bash
$ make eval                                   # green with fixed instructions
$ uv run python -m evals.regression --instructions app/data/vulnerable_instructions.md   # red
$ make redteam-gate
$ CI=1 orqi "list the traces with errors from the last 24 hours, group by root cause, markdown"
```

Watch for: exit codes · the step-summary markdown · the triage report and its own trace with cost.

<!-- Show the PR in the repo that swaps the instructions and the red check. -->

---

<!-- _class: block -->

## I · You try · Done when

- [ ] `make eval` exits 0 on fixed and 1 on vulnerable instructions
- [ ] The workflow file makes sense line by line: secrets, fork PRs, concurrency, summary
- [ ] A nightly triage run produced a markdown report

**Gotchas:** fork PRs get no secrets · static red team only in CI · pin `ORQI_VERSION`, set `CI=1` · give headless prompts an output contract.

**Ask your agent:** "Open a PR that swaps the fixed instructions for the vulnerable ones and explain the failing check from the step summary."

---

<!-- _class: lead -->

# Block J · Coding agents wired to orq

<span class="tag orange">module 13</span> Factor 11

---

<!-- _class: block -->

## J · The concept

```bash
$ orq launch claude            # this session only: gateway routing, orq MCP server, orq skills
$ orq connect --local          # permanent, per project, per capability: gateway | skills | mcp
$ orq connect --status
```

Claude Code, OpenCode, Pi, Codex, Kimi, Kilo. Every model call the agent makes is a trace with cost. Budgets apply. The 14 orq skills ship inside the CLI: `setup-observability`, `analyze-trace-failures`, `build-evaluator`, `run-experiment`, `build-agent`, `red-team`, `simulate-agent`, ...

Slash commands in Claude Code: `/orq:quickstart` `/orq:workspace` `/orq:traces` `/orq:models` `/orq:analytics`

---

<!-- _class: block -->

## J · Live demo · You try

```bash
$ orq connect --local --dry-run     # exactly which files would change
$ orq launch claude --dry-run       # the env and MCP wiring
$ orq launch claude -p "run orq doctor and summarise in three lines"
```

- [ ] `orq connect --status` shows gateway, skills and mcp for this project
- [ ] Your own coding-agent session is visible in Traces with cost per model
- [ ] You ran one orq skill end to end

**Apply it to your repo tomorrow:** `orq connect --local` → paste the `setup-observability` prompt → first trace → `analyze-trace-failures` after a week.

---

<!-- _class: input -->

## Checkpoint: what would you apply to your own app?

| Block we just did | One thing to try at work | Blocker or question |
|---|---|---|
| | | |
| | | |
| | | |

<!-- Use this slide after every two blocks. Two minutes. Write on the slide. Move blockers to the parking lot. -->

---

<!-- _class: input -->

## Parking lot

Things we skipped, questions we could not answer, requests for a follow-up.

-
-
-
-

---

<!-- _class: lead -->

# Wrap-up

<!-- 2:45. Fifteen minutes. -->

---

## What we saw against what you asked for

| You asked for | Where it lived today |
|---|---|
| Guardrails: PII detection and redaction, custom checks | Block B |
| Tracing and failure analysis | Blocks C and D |
| Agent simulation and red teaming | Block H |
| Routing, budgets, keys | Block A |
| Deployments and managed agents | Block E |
| Experiments | Block D, Block I |
| Coding agents (OpenCode, Claude Code, Pi) | Blocks C, I, J |

<!-- Fill from the checkpoint slides. Be honest about what was skipped. -->

---

## Next steps

1. **Today**: `make setup && make smoke` in this repo. Every block you missed is a module with a solution.
2. **This week**: `orq connect --local` in your own repo. Paste the `setup-observability` prompt. Get one real trace.
3. **Next week**: `make traffic`-style volume on your own app, then `analyze-trace-failures`. One evaluator per failure mode.
4. **Before the next release**: `evals.yml` in your CI. Static red team on the agents that hold tools.
5. **Follow-up session**: the parking lot decides.

**Docs** orq-ai.github.io/orq-workshop · **Repo** github.com/orq-ai/orq-workshop · **Platform docs** docs.orq.ai

---

<!-- _class: lead -->
<!-- _paginate: false -->

# Thank you

Questions, and the parking lot.
