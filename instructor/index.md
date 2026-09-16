# Facilitator notes

## Before the session

- [ ] Fresh workspace project `orq-workshop`; `make reset && make seed` from a clean clone.
- [ ] Create annotations `rating` (categorical, values `good` and `bad`) and `defects` (multi-select) in the Studio; the API returns 404 for unknown keys. Modules 02 and 17 both use them.
- [ ] Mint a Management Key with Budgets permission for module 05. Keep it out of the repo.
- [ ] GitHub: **Settings > Environments**. Create `evals` with `ORQ_API_KEY` as an environment secret and *Required reviewers* = you (deployment branches unrestricted, so PR runs can use it). Create `nightly` with the same key, no reviewers, deployment branches limited to `main`. Delete any repository-level `ORQ_API_KEY`. During module 12, approve learners' pending deployments from the Actions tab: that approval is the trust boundary between PR code and the key.
- [ ] Deploy `app/mcp_server.py` to a public URL for module 10; put it in `MCP_SERVER_URL`.
- [ ] `make traffic` twice so failure analysis has 40 traces.
- [ ] Module 14: `WS_WEBHOOK_SECRET` (`orq webhooks generate-secret`) in `.env`, `make edge` running behind a public URL (`WS_EDGE_URL`), or the shared instance up (`make edge-docker` on the host) and exposed (`cloudflared tunnel --url http://localhost:8001`, or `npx localtunnel --port 8001`), the public URL in `WS_WEBHOOK_URL`. The alert ticks every 5 minutes on data that ingests minutes late: run `make m14` at least 15 minutes before the module so a trigger exists. A new tunnel URL is fine, `make m14` re-points the notifier and the webhook.
- [ ] Module 17: the trace automation created in the Studio (**Traces > Automations**: agent is `ws-refund-agent`, sampling 100%, add to `ws-review-queue`); automations act on future traces only.
- [ ] `orqi` installed and pinned (`ORQI_VERSION`), `orq` on 8.x, `claude` or `opencode` on the demo machine.
- [ ] Render `make slides`; open `slides/facilitator.md`.
- [ ] Refresh `docs/whats-new.md` against the changelog.

## Rhythm per module

Concept in two minutes, live demo with the exact command from the README, participants run the same step, verify against **Done when**, gotchas last. Expected-output blocks in every README are real captures; if a live demo fails, show the block and move on.

## What to cut when a room runs slow

AI Gateway: skip step 4 of 01 (load balancer). AI Observability: skip the annotation step of 02; in 14 show the trigger from a `make m14` run before the session instead of waiting for the tick; in 17 skip the promote-to-dataset step. Managed Agents: skip the external knowledge base demo in 09, skip step 2 (generated personas) of 11, run only static mode in 16, show 12 as a walkthrough of the workflow files; 15 is a 15-minute demo if step 5 (the broken advisor) is dropped. Admin: fold 05 into a short demo and point at the Terraform page.

## Reset between sessions

```bash
make reset          # deletes every entity with the WS_PREFIX
make seed           # recreates them
```

Traces are not deleted. Use a new `WS_PREFIX` per cohort if traces must not mix, or a new project.

## Per-module notes

Each module README carries its own gotchas. The [seeded failures](seeded-failures.md) page lists the failures the workshop plants on purpose, so nobody debugs a feature.
