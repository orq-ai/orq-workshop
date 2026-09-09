# Facilitator notes

## Before the session

- [ ] Fresh workspace project `orq-workshop`; `make reset && make seed` from a clean clone.
- [ ] Create annotations `rating` (1 to 5) and `defects` (multi-select) in the Studio; the API returns 404 for unknown keys.
- [ ] Mint a Management Key with Budgets permission for module 05. Keep it out of the repo.
- [ ] Deploy `app/mcp_server.py` to a public URL for module 10; put it in `MCP_SERVER_URL`.
- [ ] `make traffic` twice so failure analysis has 40 traces.
- [ ] `orqi` installed and pinned (`ORQI_VERSION`), `orq` on 8.x, `claude` or `opencode` on the demo machine.
- [ ] Render `make slides`; open `slides/facilitator.md`.
- [ ] Refresh `docs/whats-new.md` against the changelog.

## Rhythm per module

Concept in two minutes, live demo with the exact command from the README, participants run the same step, verify against **Done when**, gotchas last. Expected-output blocks in every README are real captures; if a live demo fails, show the block and move on.

## What to cut when a room runs slow

AI Gateway track: fold 05 into a short demo, skip step 4 of 01 (load balancer), skip the annotation step of 02. Managed Agents track: skip the external knowledge base demo in 09, run only static mode in 11, show 12 as a walkthrough of the workflow files.

## Reset between sessions

```bash
make reset          # deletes every entity with the WS_PREFIX
make seed           # recreates them
```

Traces are not deleted. Use a new `WS_PREFIX` per cohort if traces must not mix, or a new project.

## Per-module notes

Each module README carries its own gotchas. The [seeded failures](seeded-failures.md) page lists the failures the workshop plants on purpose, so nobody debugs a feature.
