# orq.ai workshop

Hands-on training for teams building on [orq.ai](https://orq.ai). One sample app, a customer-support refund agent, grows module by module: through the AI Gateway, behind guardrails, into traces, under evaluation, as a managed agent with a knowledge base and MCP tools, attacked by simulated users and red teams, gated in CI, and driven by coding agents.

Docs site: **https://orq-ai.github.io/orq-workshop** · Slides for a 3-hour live session: `slides/`

## Quickstart

```bash
curl -fsSL https://cli.orq.ai/install.sh | sh     # orq CLI
orq auth login
git clone https://github.com/orq-ai/orq-workshop && cd orq-workshop
orq setup --local --capability gateway            # mints ORQ_API_KEY into ./.env
make setup                                        # uv sync, .env from the example
make doctor && make smoke                         # green checks + your first trace
```

Then open `modules/00-setup/README.md` or the docs site and go module by module. `make seed` creates every entity a module expects, so you can start anywhere. `make reset` deletes them all.

## The two days

| Day 1 · Control plane | Day 2 · Agents |
|---|---|
| 00 Setup | 08 Managed agents |
| 01 Gateway: fallbacks, retry, cache, load balancing | 09 Knowledge base and RAG |
| 02 Tracing: identity, thread, spans, annotations | 10 MCP servers and the MCP Gateway |
| 03 Smart routing and routing rules | 11 Simulation and red teaming |
| 04 Guardrails and PII | 12 Evals and headless agents in CI |
| 05 Budgets, keys, identities | 13 Coding agents and wrap-up |
| 06 Troubleshooting with orqi | |
| 07 Failure analysis to evaluators to experiments | |

Every module has a `README.md` (the lesson, with real expected output), a `run.py` (starter with TODOs), a `solution/` and an `agent_prompt.md` for the coding-agent track. Each ends with a **Done when** checklist.

## Two tracks

**By hand:** the Python SDK, the OpenAI-compatible gateway, the `orq` CLI, the Studio.

**With your coding agent:** `orq launch claude` (or `opencode`, `pi`, `codex`) routes the agent through the gateway and wires the orq MCP server and the orq skills. Paste the module's `agent_prompt.md`. Both tracks leave the same traces.

## Layout

```
app/refund_agent/   the sample app (never changes across modules)
app/data/           orders, policy docs, dataset, agent instructions
modules/NN-name/    README.md · run.py · solution/ · agent_prompt.md
evals/              CI regression gate (evaluatorq) and red-team gate
.github/workflows/  evals.yml · nightly-triage.yml · pr-failure-analysis.yml · docs.yml
docs/               MkDocs site (module pages include the module READMEs)
slides/             Marp deck and facilitator guide for a 3-hour session
```

## Design spine

The modules follow [12-Factor Agents](https://github.com/humanlayer/12-factor-agents). Each one names the factor it exercises and the orq surface that embodies it. See `docs/twelve-factor.md`.

## Requirements

Python 3.11 to 3.13, [uv](https://docs.astral.sh/uv/), the orq CLI 8.x, an orq.ai workspace with at least one chat model, one embedding model and one rerank model enabled. Node is only needed for `make slides` if `marp` is not installed.

## License

MIT
