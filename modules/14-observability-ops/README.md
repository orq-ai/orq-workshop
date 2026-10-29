# Alerts and webhooks

!!! abstract "The platform pushes to you"
    Modules 02 and 06 read traces after the fact. This module makes the platform push to you: a Telemetry API query gives the number, an alert watches it and opens an incident, and a webhook delivers every model call, signed, to a system you run.

| | |
|---|---|
| **Time** | 30 min |
| **Prerequisites** | module 02, `make seed`, a public URL for the receiver (see step 3) |
| **You will have** | a cost alert that opened a trigger on a burst you caused, and orq.ai events arriving signed at a receiver you run. |

Commands and names here write the default prefix `ws-`. Your entities carry your seat prefix from `.env` (`WS_PREFIX`, e.g. `ws07-`), so swap it in before you paste a command.

## Why

A trace nobody reads is a log file. Three things turn traces into operations: a number you can watch, a rule that watches it while you sleep, and a feed into the systems you already have. All three read the same trace store the Studio charts, and all three are one API call away. The fourth, a queue that collects what a human should look at, is module 17.

## The one concept to understand first

Everything here reads from the same place. The alert is a metric query on a timer; the webhook is the trace store calling you:

```python
telemetry_query(orq, compute=[{"metric": "genai.cost", "op": "sum"}], **{"from": iso(now - timedelta(hours=1))}, to=iso(now), mode="scalar", filters=[{"field": "project", "op": "eq", "values": [PROJECT]}])
orq.alerts.create(display_name="ws-cost-alert", project_id=PROJECT, signal="cost", query={"metric": "genai.cost", "filters": []},
                  condition={"comparator": "gt", "threshold": 0.002, "window": "5m", "interval": "5m"}, notifier_ids=[notifier])
orq.webhooks.create(id="ws-events-webhook", url=WS_WEBHOOK_URL, events=["llm.response", "agent.updated"], secret=WS_WEBHOOK_SECRET, ...)
```

![Diagram: your app sends traces into orq.ai; the Telemetry API aggregates them, the alert ws-cost-alert evaluates one metric every five minutes and opens a trigger that notifies a notifier; the webhook ws-events-webhook POSTs llm.response and agent.updated events, signed with X-Orq-Signature, to a receiver you run; the Studio-only trace automation into ws-review-queue is module 17's subject.](assets/observability-ops.png)

Two facts shape what you can alert on. Alerts are project-scoped, and only successful traces carry a project: a request the gateway rejected (unknown model, timeout, guardrail block) is an error trace with no project, so an error-rate alert on your project never sees it. Cost, latency and guardrail metrics come from successful traces and work. And reporting ingests in minutes, not seconds, so an alert with a five-minute window fires a tick or two after the fact.

## Steps

Open [`modules/14-observability-ops/run.py`](https://github.com/orq-ai/orq-workshop/blob/main/modules/14-observability-ops/run.py). Every step has a `TODO`. The solution is in `solution/run.py`.

### Step 1 · The number: Telemetry API

`POST /v3/telemetry/query` on the traces source. `mode: scalar` aggregates the window into one row; `group_by` turns it into a top list (one `compute` per grouped query). The SDK's `orq.telemetry.query` rejects the response in SDK 4.17 (it echoes `sort: ""`), so `entities.telemetry_query` posts the same body over REST. The older [Reporting API](https://docs.orq.ai/ai-studio/observability/reporting-api) still works for existing callers.

```bash
$ uv run python modules/14-observability-ops/solution/run.py
```

```text
── Step 1 · The number: Telemetry API ─────────────────
window   : last hour, project orq-workshop
cost     : $0.0052
errors   : rate 0.125 (genai.error_rate)
top      : last 24 hours by cost
    openai/gpt-5.6-luna          requests=18   cost=$0.0052
    openai/text-embedding-3-large requests=6    cost=$0.0000
next     : Observability > Traces in the Studio draws these same numbers
```

The error rate counts failed spans inside successful traces, such as module 01's fallback chain. The 404s and 408s you can cause from the client are not in this number: no project.

### Step 2 · The watcher: an alert on spend

`make seed` created `ws-cost-alert` (`genai.cost > $0.002` over 5 minutes, checked every 5 minutes, the fastest the plan allows) and `ws-alert-notifier`, a webhook notifier pointing at `WS_WEBHOOK_URL`. The burst is a runaway loop in miniature: refund turns until the window's spend passes the threshold with margin, fifteen at most.

```text
── Step 2 · The watcher: an alert on spend ────────────
alert    : wsvE-cost-alert <alert-id>
rule     : genai.cost gt 0.002 over 5m, every 5m
status   : ok, 1 notifier(s)
burst    : 15 turns, $0.0032 in the window (threshold $0.002)
verdict  : no trigger yet (the alert checks every 5m, telemetry lags a few minutes)
next     : orq alerts list-triggers <alert-id>; Observability > Alerts in the Studio shows the burst, the threshold line and the incident
warning  : WS_WEBHOOK_SECRET is empty, using a generated secret
fix      : put the line below in .env and restart the receiver, or signatures will not verify
secret   : WS_WEBHOOK_SECRET=<secret>
```

The first run prints `no trigger yet`: the alert ticks on its own schedule and telemetry lags. Re-run with `ALERT_WAIT=600` to poll, or check later. Take `<alert-id>` from the `alert_id` field of `orq alerts list -o json`, because ids are per workspace and do not carry over from this page:

```bash
$ orq alerts list -o json | jq '.data[] | {display_name, status, last_triggered_at}'
$ orq alerts list-triggers <alert-id> -o json | jq '.data[] | {status, severity, peak_value, opened_at}'
```

Newest first. An empty list means this run's burst has not been evaluated yet: rerun a few minutes later and it shows up on top as `open`. Earlier bursts that a quiet window closed show as `resolved`, and the alert's status goes back to `ok`. A trigger stays open until a full window passes under the threshold; the notifier is called twice per incident, open and resolve. Open **Observability > Alerts** in the Studio: the chart shows the burst, the threshold line, and the incident.

### Step 3 · The hook: a webhook into your own system

Alerts notify; webhooks stream. A workspace webhook delivers the events you subscribe to (`llm.response`, `llm.chat_completion`, `llm.embedding`, `agent.updated`, `deployment.invoked`, ...) to an HTTPS endpoint of yours, each POST signed: `X-Orq-Signature` is the HMAC-SHA256 of the raw body with the webhook's secret. [`app/edge.py`](https://github.com/orq-ai/orq-workshop/blob/main/app/edge.py) serves that endpoint (`/<WS_PREFIX>`): it verifies the signature and keeps what arrived. orq.ai cloud has to reach it, so it needs a public URL.

Three terminals:

```bash
$ orq webhooks generate-secret -o json | jq -r .secret        # -> WS_WEBHOOK_SECRET in .env
$ make edge                                                  # terminal 1: http://127.0.0.1:8001 (app/edge.py, also module 09's external KB)
$ npx localtunnel --port 8001                                # terminal 2 -> https://<random>.loca.lt, into WS_EDGE_URL in .env
$ uv run python modules/14-observability-ops/solution/run.py          # terminal 3
```

The step creates `ws-events-webhook` on `llm.response` and `agent.updated`, then fires one of each: a call to the refund agent, and a description touch on `ws-refund-agent-delegating`. Then it asks the receiver what came in.

```text
[3] webhook ws-events-webhook -> https://open-sides-sip.loca.lt/ws events=['llm.response', 'agent.updated'] receiver=app.edge
    llm.response     evt_cac18a38c2d25191dcbeeb4ae4 signature_valid=True data={"span_id": "c4a8b944f3ac8e0c", "trace_id": "7dbd755c615de9f9c8bb313e3
    agent.updated    evt_01m2ke59ez25k0khv40x2bth65 signature_valid=True data={"object": {"id": "01M2KB182JHSPMXW0YDM573XM8", "key": "ws-refund-agen
    llm.response     evt_30e44b6310ecc89953a721768d signature_valid=True data={"span_id": "c6237c108049b58b", "trace_id": "29c7efc5bf4e1127adb9713b8
```

The receiver's terminal prints the same lines as they land, with orq.ai's source IP. An `llm.response` event is the whole model span: `trace_id`, `span_id`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, usage. That is "every model call, pushed to your data warehouse" in one subscription. `agent.updated` carries `{id, key, version}`: the version bumps on every description change (1.0.0 to 1.0.1 on the first run).

```bash
$ curl -s $WS_EDGE_URL/$WS_PREFIX/events | jq '.events[] | {type, id, signature_valid}'
$ orq webhooks list -o json | jq '.items[] | {id, url, events}'
```

Signature check, the lines that matter (`app/edge.py`):

```python
expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
valid = hmac.compare_digest(expected, request.headers.get("x-orq-signature", ""))
```

The webhook URL is `<WS_EDGE_URL>/<WS_PREFIX>`, so one shared edge instance serves the whole room and `GET /<prefix>/events` shows only your deliveries. Without one (`WS_EDGE_URL` unset, the webhook at httpbin), the step still creates the webhook and fires the events, and says where to look: **Settings > Organization > Webhooks** has the delivery dashboard.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

<blockquote class="agent-prompt-frame" markdown>
Query the Telemetry API (`POST /v3/telemetry/query`) for the last 24 hours grouped by model and give me a table. Read `ws-cost-alert` and its triggers and tell me whether it has an open incident and at what peak. Then propose one more alert, latency or cost, with a threshold you justify from those numbers, and create it with `orq alerts create` using the `ws-` prefix and the notifier `ws-alert-notifier`.
</blockquote>

## Done when

- [ ] Step 1 prints a per-model table for your project and you can say which metric the alert evaluates
- [ ] `orq alerts list-triggers <alert_id>` shows a trigger with `status=open` or `resolved` and a peak above the threshold
- [ ] Your receiver printed `llm.response` and `agent.updated` with `signature_valid=True`, and you can say what a forged POST would print

## Gotchas

- `orq.telemetry.query` and `orq.alerts.list` raise `ResponseValidationError` in SDK 4.17 (the API echoes `sort: ""`, and an evaluated alert has `severity: ""`). `entities.telemetry_query`, `list_alerts` and `alert_triggers` use REST for those.
- `alerts.create` and `alerts.get` wrap the entity (`{"alert": {...}}`); `alerts.list` does not.
- Alerts are project-scoped and error traces carry no project, so pick a metric successful traces produce: cost, latency, guardrail pass rate.
- Telemetry shows the last complete minutes with a delay of a few minutes. A query for "the last 30 seconds" is empty.
- Plan limits: Free, Team and Consumption plans allow 2 alerts checked hourly; Growth, Pro and Custom allow 5-minute checks. Saving below the plan minimum returns `evaluation interval 5m is below your plan's minimum of 1h`.
- A webhook's secret has to exist before the webhook does, and the receiver needs the same one. Generate it, put it in `.env`, start the receiver, then run the step. With `WS_WEBHOOK_SECRET` empty the step generates one and prints it, and the receiver reports `signature_valid=None`.
- Webhook deliveries take 3 to 30 seconds. The step polls for 30; orq.ai retries failed deliveries later.
- A new tunnel means a new URL. `make m14` re-points `ws-events-webhook` and `ws-alert-notifier` to the current `WS_WEBHOOK_URL`; nothing is recreated.
- orq.ai switches a webhook off after 10 failed deliveries (`enabled: false`, `failure_count: 10`); a dead tunnel gets there in minutes and nothing arrives afterwards even once the URL is right. `ensure_webhook` PATCHes `enabled: true` on every run; `orq webhooks list` shows both fields, the SDK's `get` hides `enabled`.
- SDK 4.14's `webhooks.update` returns 200 and changes nothing (it sends an empty body); `PATCH /v2/webhooks/<id>` over REST works, and `ensure_webhook` uses it to re-point the URL. `webhooks.get` returns `failure_count` as `None`, so a target that stores nothing (httpbin) gives no signal at all.
- Notifiers and webhooks are different things: a notifier is where alerts and budgets send their notifications; a webhook is a subscription to workspace events. Both can point at the same URL.
- `make reset` deletes the alert, the notifier and the webhook by prefix; the trigger history goes with the alert.

## New in orq.ai 4.15 to 4.17

The Telemetry API (`POST /v3/telemetry/query`) answers cost, token, latency and evaluator questions over traces, metrics or logs in one request shape ([release 4.15](https://docs.orq.ai/changelog/release-4-15)). Monitors are custom dashboards over the same queries, with Create alert on any widget ([release 4.16](https://docs.orq.ai/changelog/release-4-16)), and alerts can watch runtime Metrics as well as Traces ([release 4.17](https://docs.orq.ai/changelog/release-4-17)).

## Go further

- Add a second alert on `genai.latency.p95` with a threshold read from step 1, and a Slack notifier (`NOTIFIER_TYPE_SLACK_WEBHOOK`).
- Subscribe the webhook to `llm.chat_completion` as well and write the receiver's events to a file: that is a trace export with no polling.

## Official docs

- [Telemetry API](https://docs.orq.ai/ai-studio/observability/telemetry-api)
- [Alerts](https://docs.orq.ai/ai-studio/observability/alerts)
- [Webhooks](https://docs.orq.ai/ai-studio/organization/webhooks)
- [Notifiers API](https://docs.orq.ai/reference/notifiers/create-a-notifier)
- [Observability quickstart](https://docs.orq.ai/ai-studio/observability/quickstart)
