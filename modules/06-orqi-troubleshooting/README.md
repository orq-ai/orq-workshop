# 06 · orqi troubleshooting

!!! abstract "Factor 11: Trigger from anywhere"
    The workspace you have been filling with traces, guardrail blocks and timeouts can be questioned from a terminal in plain language. orqi is the orq helper agent: it operates the platform, it does not build your app.

**Time:** 15 min · **Prereqs:** module 00; traffic from modules 01 to 04 in the workspace (or `make traffic`) · **You will have:** four real answers from orqi about your own workspace, a diagnosis of a seeded client-side failure, and a clear rule for when to reach for orqi versus `orq launch`.

## Why

Modules 01 to 05 produced failures on purpose: 408 timeouts from the fallback chain, 404s from bad model ids, 422 guardrail blocks. Someone has to read them. orqi turns "what broke in the last two hours" into one command, with the same MCP tools and skills your coding agent gets, minus the coding.

## The one concept to understand first

orqi embeds the pi coding agent in-process and boots with the orq AI Router as its only model provider, the 43 orq MCP tools wrapped as native tools (`orq_` prefix), the orq skills plus seven of its own (`workspace-health-check`, `investigate-root-cause`, `debug-conversation`, `optimize-cost`, `setup-guardrails`, `manage-knowledge-base`, `platform-guide`), and three subagents (`investigator`, `analyst`, `docs`). One credential covers the model and the tools. It is alpha: pin it, expect rough edges.

Every run starts with a header that tells you what was loaded:

```text
orqi (aka TonyBot) · 624ccbbd · openai/gpt-5.6-terra · 43 tools · 22 skills · 133 models · skills 9634e1d9 · ORQ_API_KEY
```

The last field is the credential source. `ORQ_API_KEY` means it used the key you exported; otherwise it reads the `orq auth login` session.

## Steps

`modules/06-orqi-troubleshooting/run.py` scripts steps 2 and 3 with `subprocess`; `make m06` runs the solution. Everything below also works typed by hand.

### Step 1 · What ships, and how it signs in

```bash
$ orqi --help
$ orq orqi --help        # the CLI installs orqi on first use; orq's own flags go in front of the word orqi
```

Expected output:

```text
orqi 0.1.0 - the orq.ai helper agent

  orqi                 interactive TUI
  orqi "<prompt>"      one-shot, prints the answer and exits
  orqi --version       print the version and exit

Sign in with `orq auth login` or export ORQ_API_KEY.
```

Use the repo key so orqi looks at the same project your app writes to, and never echo it:

```bash
$ set -a; source .env; set +a; CI=1 orqi "check workspace health"
$ env $(grep '^ORQ_API_KEY=' .env) CI=1 orqi "check workspace health"     # same thing, one line
```

`CI=1` skips the daily update check. In the interactive TUI, `/doctor` runs `orq doctor`, `/workspace` and `/whoami` show where you are, `/tools` lists the 43 tools, `/whatsnew` prints the orq changelog, `/model` offers exactly the models the workspace has enabled.

### Step 2 · Three troubleshooting prompts

```bash
$ orqi "check workspace health"
```

Expected output (trimmed, 30 s):

```text
# Workspace Health Report
**Period:** Last 24 hours, ending 2026-09-08 21:27 UTC
| Metric | Value | Status |
| Total requests | 537 | Healthy volume |
| Total cost | $1.2519 | Low spend |
| Error rate | 6.52% (35 errors) | Critical |
### Critical — elevated error rate
- Errors are mostly **HTTP 408 timeouts** on `openai/gpt-4.1`.
- The failures clustered between approximately **21:14 and 21:20 UTC**.
- One sampled trace returned a **404**, indicating at least one separate request/configuration issue.
Example timeout trace: `1ef2bd90187a45fe20d13c52c15475d3`, which ran for 8.4s before timing out.
## Recommended Actions
1. **Investigate the `gpt-4.1` timeout cluster first.** Use `investigate-root-cause` on trace `1ef2bd90187a45fe20d13c52c15475d3`.
```

Those 408s are your module 01 fallback runs (900 ms `call_timeout`). The skill pulled `get_analytics_overview`, `query_analytics` and `list_traces`, and it names the trace to look at next.

```bash
$ orqi "list the traces with errors from the last 2 hours and group them by root cause"
```

Expected output (trimmed, 1 min 50 s):

```text
**11 error traces found.**
| Root cause | Count | Evidence |
| Upstream request timeout | 10 | HTTP 408; `timeout_error`; "operation took longer than the configured timeout" |
| Invalid/unavailable model ID | 1 | HTTP 404; `openai/gpt-4o-mini-does-not-exist` |
### 1. Upstream request timeout — 10 traces
- `1ef2bd90187a45fe20d13c52c15475d3`
- `c97a01792064c4dd373ff4781daee64d`
...
### 2. Invalid model configuration — 1 trace
- `680cfc54303c748a730d96fb6901d405`
**Priority:** Fix the invalid model ID immediately. Then investigate the configured request/provider timeout and add a fallback for the timeout cluster.
```

If your workspace has too few errors, run `uv run python -m app.traffic 6` first. To pick a trace id yourself, the CLI does the same search (both bounds are required):

```bash
$ orq traces search --from 3h --to now --limit 200 --json \
    | jq -r '.data[] | select(.status=="error") | [.trace_id, .attributes.http.response.status_code, .attributes.error.type] | @tsv'
```

```text
1ef2bd90187a45fe20d13c52c15475d3	408	timeout_error
c97a01792064c4dd373ff4781daee64d	408	timeout_error
680cfc54303c748a730d96fb6901d405	404	null
```

```bash
$ orqi "why did trace 1ef2bd90187a45fe20d13c52c15475d3 fail?"
```

Expected output (trimmed, 37 s):

```text
## Root-cause report
**Trace:** `1ef2bd90187a45fe20d13c52c15475d3`
**Failure type:** Infrastructure/configuration
| Step | Result |
| Initial model: `openai/gpt-4.1` | Timed out after ~903 ms |
| Retry: `gpt-4.1` | Timed out after ~902 ms |
| Fallback: `openai/gpt-4.1-nano` | Timed out twice, each ~903 ms |
| Fallback: `openai/gpt-4o-mini` | Timed out twice, each ~902 ms |
| Overall request | Returned HTTP `408` after 8.4 s; no tokens generated |
### Why it was not an agent or tool failure
- Order lookup and policy retrieval had already succeeded: order was owned, €89, delivered 15 days ago, and not refunded.
### Fix hypothesis
**Increase the per-provider/model generation timeout above ~900 ms**, then retry this exact request.
**Confidence: High.**
```

That is the `investigate-root-cause` skill: it walked the span tree with `list_spans`, found the first upstream failure, and separated it from the tool calls that had succeeded. Compare with module 01, where you set that timeout by hand.

### Step 3 · A failure orqi cannot see in Traces

A wrong `ORQ_BASE_URL` never reaches the gateway, so there is no trace to read. The solution reproduces it without touching `.env`: the repo `.env` overrides the shell on purpose (`load_dotenv(override=True)`), so a broken copy exported in the shell would be ignored. Instead `solution/run.py` builds the same OpenAI client the app uses, with `base_url=f"{settings.base_url}/broken"` and `max_retries=0`, and passes it to `chat(..., client=broken)`:

```bash
$ make m06      # steps [1] and [2] print before the orqi calls start
```

```text
[1] traces 3h      total=200 errors=25 by http status={'502': 11, 'None': 2, '404': 1, '400': 4, '408': 7}
    cb5e6b37e6d7ac3943af6f9829e1b654  chat.openai    -
    6ad3b42f708a123e0859fe89571cbf61  chat.openai    -
    1eebd85a2346c1ee05609c0e1dc9bde0  chat.openai    -
[2] broken client  openai.NotFoundError: Error code: 404 on POST https://my.orq.ai/broken/chat/completions, x-orq-trace-id=None
```

Step [1] counts by HTTP status. By the time `make m06` ran, other modules had added 502s (a guardrail evaluator returning the wrong type) and 400s (guardrail blocks) to the 408s and the 404, and orqi's grouping in step [3.2] listed all seven causes. Your numbers will differ; the shape will not.

Paste that text into the prompt:

```bash
$ orqi "make smoke in my repo fails with this error, diagnose it and tell me what to fix: openai.NotFoundError: Error code: 404 on POST https://my.orq.ai/broken/chat/completions, empty body, no x-orq-trace-id header. The app uses the OpenAI SDK with base_url built from ORQ_BASE_URL in .env."
```

Expected output (trimmed, 31 s):

```text
**Diagnosis:** the 404 was caused by a malformed `ORQ_BASE_URL`.
The app deliberately constructs the OpenAI client URL as: base_url = f"{ORQ_BASE_URL}/v3/router"
So the expected final endpoint is: https://my.orq.ai/v3/router/chat/completions
Your failing endpoint was:         https://my.orq.ai/broken/chat/completions
**What to fix**  Set the repo's `.env` to the origin only:  ORQ_BASE_URL=https://my.orq.ai
I checked the current repo configuration, and it now resolves correctly: router_url: https://my.orq.ai/v3/router
I also ran `make smoke`; it passed and returned a gateway trace ID: f281610f09b7eeeb7d6c42f3f6478965
The lack of an `x-orq-trace-id` in the failed request is expected: the request reached a nonexistent route and never made it through the gateway.
```

Note the last two lines: orqi has `Bash` and `Read`, and it used them in your working directory. It read `config.py` and ran `make smoke` on its own. Run it from the repo you want it to look at, and nowhere you would not run a coding agent.

### Step 4 · Platform questions go to the docs

```bash
$ orqi "how do I enable PII redaction workspace-wide?"
```

Expected output (16 s):

```text
Enable it as a workspace admin:
1. Go to **Settings → Plugins**.
2. Find **PII Redaction** and turn it on.
3. Click the settings icon next to the toggle to configure: detection language, PII entity types, detection threshold, failure behavior (`on_failure`)
This applies automatically to every Router request and Agent call that does not already supply a `pii_redaction` plugin. Per-request configuration cannot disable or weaken the workspace policy—it can only be stricter.
Documentation: [Workspace-level PII redaction](https://docs.orq.ai/docs/ai-gateway/features/plugins/pii-redaction)
```

The `platform-guide` skill refuses to answer from memory: it calls `search_docs` and links the page. Module 04 did the same thing per request with `extra_body={"plugins": [...]}`.

### Step 5 · orqi versus `orq launch`

```bash
$ orq launch pi --dry-run
```

```text
binary: pi
args:   --provider orq --model openai/gpt-5.6-terra
env:
  ORQ_API_KEY=<redacted>
  ORQ_SERVER=https://my.orq.ai
  PI_CODING_AGENT_DIR=/var/folders/vz/.../T/orq-pi-2916294809
note:   a real run links 14 skills into /Users/arian/conductor/workspaces/orq-workshop/djibouti/.agents/skills for the session and removes them on exit
```

Same gateway, same skills, but now it is *your* coding agent with *your* repo as the subject. A real headless run, if `claude` is on your PATH (it is on this machine):

```bash
$ orq launch claude -- -p "run orq doctor and summarise in three lines" --allowedTools "Bash(orq doctor:*)"
```

```text
16/16 checks pass, auth good (workspace orq-research, key expires 85d). 5/5 coding agents wired, MCP present. Endpoints all reachable, gateway key healthy.
```

Nineteen seconds, four `messages.anthropic` traces under one session id, $0.30. Module 13 takes that session apart. The rule: orqi operates the platform (traces, analytics, evaluators, docs) and needs no repo; `orq launch <agent>` builds your app with orq wired in, and its own model calls become traces you pay for.

## With your coding agent

This module's agent is orqi itself. Start an interactive session with the repo key exported, or run it one-shot:

```bash
$ set -a; source .env; set +a; orqi
```

Paste `agent_prompt.md`:

> Use orqi to find the most expensive trace of the last 24 hours and explain why it cost that much.

`orq launch claude` answers the same prompt with the same MCP tools, at a higher price per turn.

## Done when

- [ ] The orqi header line shows `43 tools` and `ORQ_API_KEY`
- [ ] You have a root-cause report for a real trace id from your workspace (`orq traces search --from 3h --to now --json` finds it)
- [ ] The 404 diagnosis names `ORQ_BASE_URL` and explains the missing `x-orq-trace-id`
- [ ] `.env` is unchanged (`git diff --stat` is empty for it)
- [ ] You can state in one sentence when to use orqi and when to use `orq launch`

## Gotchas

- Alpha. Pin the release with `ORQI_VERSION=<tag>` for `install.sh` and `orqi update`; `ORQI_UPDATE_CHECK=0` or `CI=1` silences the daily check. `ORQI_SKILLS_UPDATE=0` pins the upstream skills, which otherwise refresh daily (the header went from `22 skills` to `25 skills` during this session).
- Without `ORQ_API_KEY`, orqi and `orq launch` use the login session; `launch` mints a one-hour token that cannot refresh mid-session. Export the key for anything longer.
- orqi runs shell commands in your current directory. It ran `make smoke` on its own in Step 3.
- One-shot answers take 15 s to 2 min; the `GOAL:` and `[x]` lines are progress, the answer is what follows.
- `orq traces search` needs `--from` and `--to`; `--from 3h` alone is a 400.
- The shell export from `orq setup` may belong to another workspace. `orq launch` prints `Note: ORQ_API_KEY may not belong to the workspace 'orq auth login' selected; the key wins.` That is expected here: the repo key decides where traces land.
- `.env` overrides the shell by design, which is why Step 3 breaks the client in code rather than through a temp env file.

## New in orq 4.14

`orq orqi` is a first-class CLI command in 8.x: it installs orqi on first use and hands it the login session. The Studio's CLI onboarding path (4.14) is the same flow, so a new workspace can go from sign-up to `orqi "check workspace health"` without opening the API keys page.

## Go further

`orqi "debug the conversation in thread traffic-<batch>-03"` uses the `debug-conversation` skill on the threads `make traffic` created, and `orqi "how do I cut the cost of the refund agent by half"` runs `optimize-cost` against `query_analytics` and proposes an experiment before switching models.
