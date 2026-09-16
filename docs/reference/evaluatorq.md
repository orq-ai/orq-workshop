# evaluatorq

[evaluatorq](https://github.com/orq-ai/evaluatorq) is the Python evaluation framework behind every scored run in this workshop. It answers three questions a unit test cannot: is the output any good, does the agent hold up over a real multi-turn conversation, and does it break when someone attacks it.

It is a library first and a platform client second. With no orq.ai credential it runs entirely on your machine and writes its results to a local folder; with `ORQ_API_KEY` set, the same call also lands as an **Experiment** in the Studio. Nothing is uploaded unless you opt in.

It is open source, and the repository is the reference for everything below: README, runnable examples, the full evaluator and attack catalogues, and the issue tracker:

[:octicons-mark-github-16: orq-ai/evaluatorq](https://github.com/orq-ai/evaluatorq){ .md-button .md-button--primary }
[:octicons-book-16: Documentation](https://orq-ai.github.io/evaluatorq/){ .md-button }

## The three things it runs

| | What it does | Where it shows up here |
|---|---|---|
| **Evaluation** | runs a job over a dataset and scores each row with evaluators you write (or built-ins like an LLM judge) | [module 07](../modules/07.md), [module 12](../modules/12.md) |
| **Agent simulation** | a user-simulator LLM plays a persona with a goal and holds a multi-turn conversation with your agent; a judge scores the transcript | [module 11](../modules/11.md) |
| **Red teaming** | an attacker model works through OWASP categories (Agentic Top 10 and LLM Top 10) and a judge decides whether each attack landed | [module 16](../modules/16.md) |

All three share one shape: a **target** (the thing under test), **cases** (rows, personas or attacks), and **judges** (what counts as a pass). Change the target, keep the cases, and two runs compare.

## A minimal evaluation

```python
from evaluatorq import DataPoint, evaluatorq, job

@job()
async def refund_agent(dp: DataPoint) -> str:
    return chat(dp.input).text          # whatever your agent is

results = await evaluatorq(
    name="refund-quality",
    jobs=[refund_agent],
    data=[DataPoint(input="refund ord_a1", expected="24.99")],
    evaluators=[my_scorer],
)
```

`evals/regression.py` in this repo is that pattern at full size: one job, a JSONL dataset, three scorers, and a mean-per-scorer threshold that exits 1 on a regression.

## Install

The workshop pins `evaluatorq[redteam,dashboard]`. The extras are additive:

```bash
$ uv add evaluatorq                        # core evaluation only
$ uv add "evaluatorq[simulation]"          # + agent simulation
$ uv add "evaluatorq[redteam]"             # + red teaming
$ uv add "evaluatorq[dashboard]"           # + the local dashboard
$ uv add "evaluatorq[all]"                 # everything
```

There are also framework extras (`langchain`, `langgraph`, `openai-agents`, `pydantic-ai`, `crewai`, `otel`) because the target can be any of those, a plain async function, or an orq-hosted agent by key.

!!! warning "`eq dashboard` needs its own extra"
    Without `evaluatorq[dashboard]` the command refuses to start and only the older, deprecated `eq sim ui` / `eq redteam ui` Streamlit views work.

## Local or on orq.ai

The same call does both. The credential is the switch:

| | Local only | With `ORQ_API_KEY` |
|---|---|---|
| **Where results go** | `.evaluatorq/runs/` (red team), `.evaluatorq/sim-runs/` (simulation) | the same files, **plus** an Experiment run in the Studio |
| **How you read them** | `eq dashboard` on `127.0.0.1:8080` | the Studio, or the local dashboard, or both |
| **Who else can see them** | nobody (nothing leaves the machine) | everyone with workspace access |
| **History** | whatever is in the folder | every run, versioned, comparable, with per-row verdicts |
| **Which models you can call** | any provider key you hold | the orq AI Router, so the calls are traced, costed and budgeted |
| **Cost visibility** | the run's own token counts | the run **and** its spend, against budgets and identities |

Two details that bite:

- **The SDK does not auto-save; the CLI does.** `simulate()` and `red_team()` default to `save=False`, so a Python script uploads to Experiments and leaves nothing on disk, and `eq dashboard` then shows an empty section. Pass `save=True`. The `eq` CLI saves without being asked.
- **An upload with no path lands in the Default project.** Pass `path=` (this repo uses `settings.path`) to pin the Experiment where the rest of your work lives.

## When to use which

**Stay local when** you are iterating. A prompt change you will make twenty times in an hour does not need twenty Experiment rows. Local runs are also the honest answer when the data cannot leave your machine, when you are offline, or when you are evaluating a model that is not behind the router.

**Send it to orq.ai when** the result is evidence someone else will act on:

- **A regression gate in CI.** The exit code is what fails the build, but the Experiment is what a reviewer reads to see *which* row dropped ([module 12](../modules/12.md)).
- **Comparing two versions.** Two Experiment runs of the same dataset sit side by side with per-row verdicts; two local JSON files do not ([module 07](../modules/07.md)).
- **Anything with a cost question.** Router calls are traced and budgeted, so "what did this eval cost" has an answer ([module 05](../modules/05.md)).
- **Work that outlives the session.** A local folder is a scratch pad; an Experiment is a record with a URL you can paste into a ticket.

The practical answer for most teams is *both*: develop against the local dashboard, then let CI run the same file with a key set so the result is durable. The code does not change between the two; only the environment does.

## Where to go next

- The repo: [orq-ai/evaluatorq](https://github.com/orq-ai/evaluatorq) (README, examples, issues)
- The docs: [orq-ai.github.io/evaluatorq](https://orq-ai.github.io/evaluatorq/)
- In this workshop: [module 07](../modules/07.md) builds the evaluators, [module 11](../modules/11.md) simulates customers, [module 16](../modules/16.md) attacks the agent, and [module 12](../modules/12.md) puts the whole thing in CI.
