# Wrap-up: your own repo

The core path took the refund agent around the loop once. This page does the same for your own application, one stage at a time, with your coding agent doing most of the typing. Budget an afternoon for the first pass; the later ones are the loop itself.

## Before you start

- `orq connect --local --dry-run` in your repo, read the file list, then `orq connect --local`. Commit `.mcp.json` or `opencode.json` if the team should share the wiring; keep `.claude/skills` and `.agents/skills` out of git (they are symlinks into `~/.orq/snapshot`).
- `npx skills add orq-ai/assistant-plugins` installs the orq.ai skills in any coding agent that supports skills; `orq launch <agent>` runs one through the gateway with no config at all.
- One project in the Studio for this app, one key minted into its `.env` with `orq setup --local`.

## One pass around the loop

<div class="steps" markdown>

1. **Build.** Nothing to change yet. Write down, in one paragraph, what the agent decides on its own and what it hands to a person. That paragraph is the start of your instructions file and of your first dataset.
2. **Route and protect.** Point the client at the gateway. Prompt: *"Use the setup-observability skill on this repo. Detect the framework, prefer the AI Router mode, set `service.name`, and stop after the baseline trace is verified."* Then add a fallback and a cache field to the one call that costs the most.
3. **Trace.** A good first trace has a model span with `provider/model`, tokens and cost filled in, a name you would search for, and the request route. Add `identity`, `thread` and `metadata` so a complaint can be found by customer and conversation.
4. **Find failures.** After a week of traffic: *"Use the analyze-trace-failures skill on the last 7 days of traces for project X."* Let it build the taxonomy before you write an evaluator. Three failure modes with counts is the deliverable.
5. **Evaluate.** For the top failure mode: *"Use the build-evaluator skill for `<failure mode>` and validate it on 20 labeled traces."* Then twenty rows in a dataset, half of them the cases the taxonomy named.
6. **Gate and monitor.** A regression run on every pull request that touches the prompt (`evaluatorq` exits non-zero), one cost alert on the project, one webhook into the system your team already watches.

</div>

## Done when

- [ ] A trace from your app, searchable by customer and conversation, with cost on the model span
- [ ] A written failure taxonomy with counts, from real traffic
- [ ] One evaluator that fails on the top failure mode and passes on a fixed answer
- [ ] A dataset of at least 20 rows, and an Experiment run comparing two versions of your prompt
- [ ] A CI job that goes red when the evaluator's pass rate drops

## With your coding agent

<blockquote class="agent-prompt-frame" markdown>
Read this repository and tell me which stage of the loop it is at: traced or not, which failure modes are known, which evaluators exist, what runs in CI. Then propose the single next step from the wrap-up page of the orq.ai workshop and do it, stopping before anything that changes production behavior.
</blockquote>

## Keep going

The electives, listed by stage on [Already on orq.ai](already-on-orq.md), each add one capability to this loop: a knowledge base, an MCP gateway, simulated customers, a red team, human review. Take the one that matches the failure mode you found first.
