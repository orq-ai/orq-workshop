# Facilitator guide: KickstartAI TechDays

"Is Your Agent Behaving Like You Expect? Testing With Evals". Thursday 15 Oct, Circa Amsterdam. Two hours including Q&A, about 30 senior engineers. Deck: `slides/deck.md`, rendered with `make session S=techdays-2026`.

The session follows one agent through four steps: build it, simulate customers against it, read the simulated traces with Insights, turn the failure Insights finds into an eval that gates CI. The principle: get to simulation fast, because evals without data are theory. v1 of the agent is `vulnerable_instructions.md`, so the simulation surfaces a real failure; the fix is `fixed_instructions.md`. Each step reuses a module's solution, so every command has an expected-output block in that module's README to fall back on.

## Timing

| Clock | Block | Min | Slides | Source | Hands-on |
|---|---|---|---|---|---|
| 0:00 | Welcome, hands count, how today works | 5 | 1 to 3 | | |
| 0:05 | Onboarding: QR → key by email → `.env` → `make setup && make orq-doctor && make gateway-check` | 20 | 4 to 5 | module 00 | walk the room |
| 0:25 | 1 · The refund agent: loop in code, `make seed-workspace`, managed copy, one trace | 15 | 6 to 8 | modules 00, 08 | 7 concept + 8 run |
| 0:40 | 2 · Agent simulation: personas × scenarios, criteria, run against v1 (vulnerable prompt), `eq dashboard` | 35 | 9 to 14 | module 11 | 10 concept + 25 TODOs |
| 1:15 | 3 · Trace insights: `make m18` on your own sim traces, failure clusters in `eq dashboard` → Insights | 25 | 15 to 18 | module 18 | 5 concept + 20 click |
| 1:40 | 4 · From insight to eval: one binary evaluator for the failure, swap to fixed prompt, re-run, CI gate in one slide | 12 | 19 to 22 | modules 07, 12 | demo |
| 1:52 | Take home + Q&A | 8 | 23 to 24 | | |

Slides 25 onwards are an appendix (module 07 taxonomy and experiment, testing the judge, red teaming). They are not presented; use them for questions.

**Cut order if late:** block 4 to demo-only (slides 20 and 22, skip the re-run), then shorten block 1 to the demo slide. Never cut block 3: it is the part the room has not seen.

## Who runs what

Two facilitators. During onboarding and the hands-on parts of blocks 2 and 3, both walk the room. Otherwise one drives the demo screen and the other keeps an eye on the room and on per-seat spend (see below).

## Before the session

- [ ] Latest orq CLI on the demo machine: `curl -fsSL https://cli.orq.ai/install.sh | sh`, then `orq --version`. Version used: `________`.
- [ ] Demo workspace clean: `make reset-workspace && make seed-workspace` from a fresh clone, with a key claimed through the kickstart page like a participant's.
- [ ] `uv run python modules/11-simulation/run.py --only=1,3` and `make m18` each run once today. Keep the terminal output in a scratch file as fallback.
- [ ] `uv run eq dashboard` open in a browser tab with the Agent Sim run and the Insights run above loaded.
- [ ] `make regression-eval` and `make regression-eval-vulnerable` run once: exit 0 and exit 1.
- [ ] `orq launch claude` works on the demo machine, and `npx skills add orq-ai/assistant-plugins` is installed for the `orq-recommend-evaluators` line on slide 20.
- [ ] Concurrency dry run: `make seed-workspace`, module 11 step 1 and `make m18` from four laptops at once on the workshop workspace. Note where it breaks, and the cost of one full seat run (Home → usage per API key): `________`.
- [ ] Put the real passcode on slide 4 in the local copy you present from. Never commit it.
- [ ] `make session S=techdays-2026`, and keep `slides/deck.html` (self-contained) on a USB stick for the venue. If the globally installed `marp` fails (it does on Node 26), run `make session S=techdays-2026 MARP="npx -y @marp-team/marp-cli@latest"`.

### Participant access

One shared workshop workspace. Each participant claims their own key on the day:

1. Open https://orq-kickstart.vercel.app (the QR code on slide 4 points there).
2. Enter their email and the passcode the hosts set. The slide shows `PASSCODE` as a placeholder; the real passcode is set by the hosts and never committed.
3. They get an email with a ready-to-paste `.env` block: `ORQ_API_KEY`, `ORQ_PROJECT`, `WS_PREFIX=ws<NN>` and the model lines.
4. `cp .env.example .env`, paste the block, then `make setup && make orq-doctor && make gateway-check`.

The per-seat `WS_PREFIX` (`ws01`, `ws02`, ...) keeps 30 copies of the agent apart: keys become `ws07-refund-agent`, `ws07-refund-agent-vulnerable`. `make reset-workspace` deletes by prefix afterwards.

- Prerequisites mail (Anastasia sends it Wednesday): clone the repo, install `uv`, run `make setup`, bring a laptop that allows `curl | sh`. Fallback for anyone who cannot install: follow on the demo screen and read the expected-output blocks. Say this up front so nobody feels behind.
- No email after two minutes: check spam first, then a facilitator.
- Do not debug a laptop in front of the room. A stale `ORQ_API_KEY` exported in the shell beats `.env` in some tools: `set -a; source .env; set +a`.

### Models

The workshop workspace enables GPT-6 Luna, DeepSeek Flash, `typesafe/jev-latest` (the Insights classifier) and OpenAI text-embedding-3 small and large. Every model name comes from `.env`: the defaults in `.env.example` and the lines in the key email name these models, so nobody edits a model name by hand. Model names are deliberately not on the slides.

### Spend

Each seat's key has a $2 budget. Home → usage per API key (orq 4.16) shows requests, cost and tokens per key: keep it open on the second facilitator's laptop and watch for a seat running away (a loop, or someone raising `max_turns`).

## Block notes

**Opening and onboarding.** Count hands for "structured evals on an agent in production today" and come back to the number at the end. Leave slide 4 up for the first five minutes of onboarding, then slide 5. By 0:25, move on whether or not every laptop is green; the rest can follow on screen and catch up in block 2.

**1 · The refund agent.** Keep it to fifteen minutes. The point to land is that the agent is a function, transcript in and transcript out, which is what makes simulation cheap. The code on slide 7 is `run_turn` from `app/refund_agent/agent.py`, trimmed (the step that appends the model's text and `function_call` items is left out). `orq agents retrieve` (not `get`) shows the managed copy. Open one trace in the Studio: tool calls, cost, the agent version on every span.

**2 · Agent simulation.** Run against v1, the vulnerable prompt. What our runs showed (13 Oct, four conversations per run: 2 personas × 2 scenarios, max 4 turns): both post-window `ord_a3` conversations broke the `must_not_happen` criterion about manager approval; in one run v1 really issued the EUR 42.50 refund; the fixed prompt broke 0 rules. Two things to say out loud:

- The refund tool enforces the 30-day window, so v1's failure is often "tries and gets blocked by the tool". The judge sees the transcript text only, not tool calls, so the criterion is written about what the agent says.
- Wording the criterion is the work. A vaguer version of that criterion flagged the fixed prompt once, because the fixed prompt passed the claim on to a human. The bracket "(passing the claim on to a human reviewer is fine)" is the fix.

The participant TODOs are in `modules/11-simulation/run.py`: a second persona and the post-window scenario. People who finish early run step 3 (`--only=3`), the two-harness comparison on slide 14. The built-in `agent:<key>` target cannot run your function tools: it drops the call, the answer is empty and the score is 0.00, while `ManagedRefundTarget` on the same agent and scenario scores 1.00. Re-verified on evaluatorq 1.70.1, 13 Oct.

**3 · Trace insights.** `make m18` simulates module 11's personas and scenarios against the managed v1 agent (`ws<NN>-refund-agent-vulnerable`, through `ManagedRefundTarget`), then runs `eq insights --agent ws<NN>-refund-agent-vulnerable --dimension failure --dimension intent --label made_errors`. Insights reads the traces, summarises each one, clusters the summaries and names the clusters, so it finds failures nobody wrote a criterion for. Our run on 14 traces: one failure cluster, "Used an unsupported post-window refund reason" (6 traces); `made_errors` yes on 12 of 14; Insights cost $0.0067 for the 14 traces. Participants' counts will differ. Point out that the cluster is wider than the criterion: manager approval or any other reason not on the allowed list.

Then `uv run eq dashboard` → Insights tab. Two Studio features help here: the rebuilt Traces page (orq 4.16) filters on any attribute or metadata field and saves views with the filter in the URL, so each participant can filter on their own agent name; `orq traces conversation <id>` (orq 4.15) prints one trace as a readable conversation. Push people to read two traces from the cluster before they accept its name.

**4 · From insight to eval.** Demo only. The cluster becomes one binary evaluator in the style of module 07's `refund_when_should_refuse`: code where the tool call shows it, a judge for what only the words show. Then set `VARIANT = "fixed"` in module 11 and re-run step 1 (0 rules broken on our run). The figure on slide 21 is the module 11 README run on the fixed prompt, from before the manager-approval criterion was added; it shows the shape (refusal reads as goal not achieved, rules broken none), not today's numbers. Slide 22 is the module 12 CI gate: `make regression-eval` exits 0, `make regression-eval-vulnerable` exits 1. Since orq 4.15 evaluators skip failed Agent runs, so scores reflect completed runs only. The "Ask your agent" line uses orq Skills from 4.16: `orq-recommend-evaluators` reads the agent's instructions, tools and recent traces and proposes up to five evaluators; `orq-evaluator-alignment` runs a jury test of a judge prompt. Install with `npx skills add orq-ai/assistant-plugins`.

**Appendix.** Not presented. If someone asks about red teaming: static mode only, deterministic, about three minutes. Do not show `modules/16-red-teaming/assets/red-team-loop.png`: its caption (judge flagged one, store saw two refunds) contradicts the run output in the same README (judge flagged two, store saw one). The module 07 judge prompt has since been fixed for the "change of mind" case (`app/data/judge_prompt.md` now says any reason is valid in-window); module 07's README still describes the old behaviour.

## Known gaps

- **"At scale" in the abstract.** The material runs 20 dataset rows and a handful of simulated conversations (14 traces in our Insights run). Do not claim 100+ conversations. Until there is a script for it, say "the same call, with more personas and `datapoint_parallelism`", and do not show a number you have not run.
- **Judge alignment** is a pointer (`orq-evaluator-alignment`, appendix slides), not a lab. The full version (100+ labels, dev and test split) is in the "Go further" section of module 07.
- **The `agent:<key>` target in `eq sim run`** drops function tool calls (module 11 step 3a; re-verified on evaluatorq 1.70.1, 13 Oct). Do not run a CLI simulation against the managed agent live and present the score as the agent's.

## Demo fallbacks

Every module README has real expected-output blocks. If a live command fails, show the block, name the cause, move on. Common causes: rate limits from a shared workspace, a stale `ORQ_API_KEY` exported in the shell (`set -a; source .env; set +a`), judge drift moving a number by a few points.

## Reset after the session

```bash
make reset-workspace
```

Run it once per prefix used. Traces stay.
