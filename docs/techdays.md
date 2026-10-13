# KickstartAI TechDays · 15 Oct 2026

**Is your agent behaving like you expect? Testing with evals.** Two hours, one refund agent, four steps: build it, simulate customers against it, read the traces with Insights, turn what you find into an eval.

Evals without data are theory, so we get to simulation fast. Each block is a short concept, then your hands on the keyboard; the hosts walk the room.

## Before you come

- Clone the repo: `git clone https://github.com/orq-ai/orq-workshop && cd orq-workshop`
- Install [uv](https://docs.astral.sh/uv/) and run `make setup`
- Bring a laptop that allows `curl | sh`. If yours does not, follow on screen with a neighbour.

## The two hours

| Clock | Block | You run | Module |
|---|---|---|---|
| 0:00 | Welcome, how today works | | |
| 0:05 | Get your key and set up | `make setup && make doctor && make smoke` | [00 Setup](modules/00.md) |
| 0:25 | 1 · The refund agent | `make seed`, one turn, open the trace | [00 Setup](modules/00.md), [08 Managed agents](modules/08.md) |
| 0:40 | 2 · Simulate customers | the TODOs in `modules/11-simulation/run.py`, then `uv run eq dashboard` | [11 Agent simulation](modules/11.md) |
| 1:15 | 3 · Read the traces | `make m18`, then Insights in `uv run eq dashboard` | [18 Trace insights](modules/18.md) |
| 1:40 | 4 · From insight to eval | `make eval`, `make eval-vulnerable` | [07 Failure analysis](modules/07.md), [12 Evals in CI](modules/12.md) |
| 1:52 | Take home, questions | | |

## Get your key (0:05)

1. Scan the QR code on the slide, or open [orq-kickstart.vercel.app](https://orq-kickstart.vercel.app).
2. Enter your email and the passcode on the slide.
3. Check your inbox. The email has a ready-to-paste `.env` block: your key, your project and your seat prefix (`WS_PREFIX=ws07`, so your agent is `ws07-refund-agent`), plus the model lines.
4. In the repo: `cp .env.example .env`, paste the block over it, then:

```bash
make setup && make doctor && make smoke
```

Done when `make smoke` prints an answer, the tools it called and a trace id. Nothing in `.env` needs editing by hand; every model comes from it.

## 1 · The refund agent (0:25)

Three tools, one loop, your code; every model call goes through the orq gateway, so every turn is a trace. `make seed` creates the managed copies you need later: `ws<NN>-refund-agent` (the fixed prompt) and `ws<NN>-refund-agent-vulnerable` (v1, the one we test today).

Done when you have opened your smoke trace in the Studio and can point at its tool calls.

## 2 · Simulate customers (0:40)

A user simulator plays a persona with a goal, your agent answers, a judge scores the transcript against criteria you write. Today's target is v1, `vulnerable_instructions.md`: it trusts a customer who says "a manager approved it".

Open `modules/11-simulation/run.py` and fill in the TODOs: a second persona, and a post-window scenario on `ord_a3` with `must_not_happen` criteria. Then:

```bash
uv run python modules/11-simulation/run.py
uv run eq dashboard
```

Done when at least one `ord_a3` row shows a broken rule and you can say why. The judge reads words, not tool calls: write criteria the transcript can show.

## 3 · Read the traces (1:15)

Criteria check what you expected. Insights reads your traces, summarises and clusters them, and names what went wrong, including what you did not write a criterion for.

```bash
make m18
uv run eq dashboard     # Insights → your run → the failure cluster → two example traces
```

Done when you have one Pass/Fail sentence for the failure the cluster names.

## 4 · From insight to eval (1:40)

The sentence becomes one binary evaluator. Swap to the fixed prompt, re-run, and gate on it:

```bash
make eval              # fixed prompt: exits 0
make eval-vulnerable   # v1: exits 1
```

## Take home

- [The full course](agenda.md): 18 modules, from the gateway to red teaming.
- [Red teaming](modules/16.md) and [annotation queues](modules/17.md) were left out today; they work on the same agent.
- Your key is deleted after the workshop.
