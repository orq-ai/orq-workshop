# Facilitator guide: KickstartAI TechDays

"Is Your Agent Behaving Like You Expect? Testing With Evals". 90 minutes of workshop, then 15 minutes of Q&A. About 20 senior engineers. Deck: `slides/techdays.md`, rendered with `make slides DECK=techdays`.

The session follows one agent through five steps: build it, add evals, simulate customers against those evals, test the evals themselves, attack it. Each step reuses a module's solution, so every command has an expected-output block in that module's README to fall back on.

## Timing

| Clock | Segment | Slides | Source |
|---|---|---|---|
| 0:00 | Opening, "demos are not evidence", how it works, `make smoke` | 1 to 3 | module 00 |
| 0:08 | 1 · Build the agent: the loop, `make seed`, local vs managed | 4 to 6 | modules 00, 08 |
| 0:18 | 2 · Add evals: traces, taxonomy, evaluators, experiment | 7 to 11 | module 07 |
| 0:43 | 3 · Simulate customers: personas, scenarios, criteria, harness | 12 to 17 | module 11 |
| 1:03 | 4 · Test the evals: judge failure modes, hand labels, agreement | 18 to 20 | modules 07, 11, 12 |
| 1:15 | 5 · Attack it: red team both prompts, the CI gate | 21 to 23 | modules 16, 12 |
| 1:25 | What to take home | 24 | |
| 1:30 | Q&A until 1:45 | 25 | |

Blocks 2 and 3 carry the session. If time runs short, cut block 5 to the CI slide only, then shorten block 1 to the demo slide. Never cut block 4: it is the part most teams have not seen.

## Who runs what

Two facilitators. One drives the demo screen, the other walks the room and keeps an eye on the Studio for participants who fall behind. Swap at the break between block 3 and 4 if you want, there is no formal break.

## Before the session

- [ ] A demo workspace, clean: `make reset && make seed && make traffic` from a fresh clone.
- [ ] `make m07`, `uv run python modules/11-simulation/solution/run.py --only=1,3` and `uv run python modules/16-red-teaming/solution/run.py --only=1` each run once today. Keep the terminal output in a scratch file as fallback.
- [ ] `uv run eq dashboard` open in a browser tab with the runs above loaded.
- [ ] The block 2 Experiment open in a Studio tab (it lands in the **Default** project).
- [ ] `make eval`, `make eval-vulnerable`, `make redteam-gate` run once: exit 0, 1, 0.
- [ ] `orq launch claude` works on the demo machine, for the "Ask your agent" lines.
- [ ] `make slides DECK=techdays` and the PDF copied to a USB stick for the venue.

### Participant access

Default plan, until decided otherwise: one shared workshop workspace, a key minted per seat in advance, and a distinct `WS_PREFIX` per seat (`ws01`, `ws02`, ...; keys become `ws01-refund-agent`) so the 20 copies of the agent do not collide. Hand each person a card with the key and prefix. `make reset` deletes by prefix afterwards.

- Corporate laptops often block `curl | sh`. Anyone who cannot install follows along on the demo screen and reads the expected-output blocks. Say this up front so nobody feels behind.
- Twenty people running simulations and judges at once share one workspace's rate limits. Run `make traffic` and a simulation from three or four laptops at once beforehand to see where it breaks.
- A prerequisites mail before the day (clone the repo, `make setup`, `uv` installed) saves the first ten minutes.

## Block notes

**1 · Build the agent.** Keep it under ten minutes. The point to land is that the agent is a function, transcript in and transcript out, which is what makes simulation cheap in block 3. `orq agents retrieve` (not `get`) shows the managed copy.

**2 · Add evals.** The taxonomy table on slide 9 is from the module 07 README run; the live run will differ. Point out that one failure is on the *fixed* prompt: the "moving abroad" bulk refund. That is the argument for reading traces before writing evals. The starter's TODO for participants is the `metadata.batch` filter in `traffic_traces()`.

**3 · Simulate customers.** Slide 15 is the one to slow down on: `goal not achieved` on `ord_a3` is the agent correctly refusing. Gate on the `must_not_happen` criterion. Step 3 (two harnesses, 0.00 vs 1.00 on the same agent) is the surprise of the block; leave it on screen while people read.

**4 · Test the evals.** Run the hand-labelling live on five rows of the block 2 Experiment: read the row, the room calls pass or fail, then reveal the judge's verdict. Disagreements are the content. Everything on slide 19 comes from a module README; do not claim more than that. The judge prompt has since been fixed for the "change of mind" case (`app/data/judge_prompt.md` now says any reason is valid in-window); module 07's README still describes the old behaviour.

**5 · Attack it.** Static mode only, it is deterministic and finishes in about three minutes. The line to land is the disagreement between the judge and the order store: `ord_a3` really refunded. Do not show `modules/16-red-teaming/assets/red-team-loop.png`: its caption (judge flagged one, store saw two refunds) contradicts the run output in the same README (judge flagged two, store saw one). If the run is slow, show the expected output from the module 16 README instead.

## Known gaps

- **"At scale" in the abstract.** The material runs 20 dataset rows and a handful of simulated conversations. A 100+ conversation simulation shown in `eq dashboard` would back the claim; there is no script for it in the repo yet. Until there is, say "the same call, with more personas and `datapoint_parallelism`", and do not show a number you have not run.
- **Judge alignment** is a talk-through and a five-row exercise, not a lab. The full version (100+ labels, dev and test split) is in the "Go further" section of module 07.
- **The `agent:<key>` target in `eq sim run`** drops function tool calls (module 11 step 3a). Do not run a CLI simulation against the managed agent live and present the score as the agent's.

## Demo fallbacks

Every module README has real expected-output blocks. If a live command fails, show the block, name the cause, move on. Common causes: rate limits from a shared workspace, a stale `ORQ_API_KEY` exported in the shell (`set -a; source .env; set +a`), judge drift moving a number by a few points.

## Reset after the session

```bash
make reset
```

Run it once per prefix used. Traces stay.
