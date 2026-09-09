# Facilitator guide for a live session

## Timing

| Clock | Segment | Slides |
|---|---|---|
| 0:00 | Opening, how today works, "how do you use orq today" | 1 to 3 |
| 0:12 | The map: picture, refund agent, 12-factor spine, what's new | 4 to 8 |
| 0:27 | Vote | 9 |
| 0:32 | Block 1 (25 to 30 min) | block section |
| 1:00 | Block 2 | |
| 1:25 | Checkpoint (2 min), break (10 min) | checkpoint slide |
| 1:37 | Block 3 | |
| 2:05 | Block 4 | |
| 2:30 | Checkpoint, short break | |
| 2:40 | Block 5 if time, else start wrap-up | |
| 2:45 | Wrap-up: what we saw vs asked, next steps, parking lot | last 4 slides |
| 3:00 | Close | |

Four blocks fit comfortably. Five fit if the room is fast and setup was done before the session.

## Vote to order

Take the top four or five. Then order them so prerequisites come first:

| If the room picked | Run in this order |
|---|---|
| anything with D, H or I | C first (traces are the evidence everywhere) |
| E, F or G | E before F and G (both attach to the managed agent) |
| I | D or H before I (the gate reuses the evaluators or the red team) |
| J | last, it doubles as wrap-up |
| a tie | default: C, B, D, H, J |

For this client's survey (guardrails, tracing and failure analysis, simulation and red teaming, coding agents), the expected result is B, C, D, H, J.

## Before the session

- `make reset && make seed && make traffic` from a clean clone in the demo workspace.
- Annotations `rating` and `defects` created in the Studio.
- A Management Key for block A, exported in the demo shell only.
- `app/mcp_server.py` deployed to a public URL, `MCP_SERVER_URL` set, for block G.
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
