# Facilitator guide for a live session

## Timing

| Clock | Segment | Slides |
|---|---|---|
| 0:00 | Opening, how today works, "how do you use orq today" | 1 to 3 |
| 0:12 | The map: picture, refund agent, what's new | 4 to 8 |
| 0:27 | What you asked for: confirm, do not re-open | 9 |
| 0:30 | Block 1 · Own your agent | block section |
| 1:00 | Block 2 · Managed agents | |
| 1:30 | Checkpoint (2 min), break (10 min) | checkpoint slide |
| 1:42 | Block 3 · Knowledge base and RAG | |
| 2:17 | Block 4 · MCP servers and the MCP Gateway | |
| 2:42 | Wrap-up: what we saw vs asked, next steps, parking lot | last 4 slides |
| 3:00 | Close | |

Four blocks, fixed, no vote. They fit with ten minutes of slack; the slack goes to whichever block the room leans into.

## Why these four, and not a vote

Pierre-Louis and Vansh both named the same three gaps in writing: managed agents, the Knowledge Base API and RAG with internal **and** external search engines, and MCP servers with the MCP gateway. Vansh added a fourth, and was most emphatic about it: building agents in their own framework (LangGraph, raw Python SDK) with orq as the infrastructure layer around it: prompts, tracing, tool tracing, routing.

Both also said what they do **not** need: *"Everything linked to routing, model testing / selection, monitoring … is easier to grasp with documentation and almost everyone in the team already played with it."*

So the deck runs those four in depth. Voting would re-open a question they already answered, and the old survey answer (guardrails, tracing, simulation and red teaming) is superseded; do not fall back to it.

## If the room wants something else

The appendix opens with one slide per module (00 to 17): abstract, time, prerequisites, outcome, `make mNN`, and which block covers it. Use it as the index when someone asks "where is X". After it come the other blocks, complete: A gateway and routing, B guardrails and PII, C tracing and orqi, D failure analysis to experiments, H simulation and red teaming, I evals in CI, J coding agents. Jump to one by page. If you swap, drop Block 4 first: it is the shortest and the most self-contained.

## Before the session

- `make reset && make seed && make traffic` from a clean clone in the demo workspace.
- Annotations `rating` and `defects` created in the Studio.
- `uv sync --extra langgraph`, then `uv run python examples/own-your-agent.py` once: block 1 needs all three legs green, and the LangGraph leg waits ~10s for its trace to index.
- A Management Key only if you plan to fall back to appendix block A, exported in the demo shell.
- `app/mcp_server.py` deployed to a public URL, `MCP_SERVER_URL` set, for block 4.
- `orqi` installed and pinned; `orq` 8.x; `claude` or `opencode` on the demo machine.
- Every `make mNN` run once today; keep the terminal output in a scratch file as fallback.
- `docs/whats-new.md` refreshed.

## Demo fallbacks

Every module README has real expected-output blocks. If a live command fails, show the block, name the cause, and move on. Common causes: rate limits from a shared workspace, a fallback that did not trigger because the primary was fast, a fresh datasource still processing.

## Participation

- Slide 3 is filled live; keep it visible on a second screen.
- The checkpoint slide after every two blocks: two minutes, everyone writes one line.
- The parking lot slide stays open. Anything skipped becomes a follow-up item in the wrap-up.

## Reset after the session

```bash
make reset
```

Traces stay. Use a new `WS_PREFIX` per cohort if they must not mix.
