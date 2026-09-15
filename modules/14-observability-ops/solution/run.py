# %% [markdown]
# # 14 · Alerts, automations and framework hooks
#
# Modules 02 and 06 read traces after the fact. This module makes the platform push to you: a
# Reporting API query gives the number, an alert watches it and opens an incident, and a webhook
# delivers every model call, signed, to a system you run. Three steps; the review queue that
# collects traces for a human is module 17.
#
# | | |
# |---|---|
# | **Time** | 30 min |
# | **Prerequisites** | module 02, `make seed` |
# | **You will have** | a cost alert that opened a trigger on a burst you caused, and orq events arriving signed at a receiver you run |
#
# This file is both the solution script (`make m14`) and the notebook source (`make notebooks`).
# Run the cells top to bottom.

# %%
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta

import httpx

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import (
    ALERT_THRESHOLD_USD,
    alert_triggers,
    ensure_alert,
    ensure_notifier,
    ensure_webhook,
    list_alerts,
    project_id,
    reporting_query,
)

orq = make_orq()
PROJECT = project_id(orq)
AGENT = settings.key("refund-agent")  # ws-refund-agent: its calls are attributed to the project
DELEGATING = settings.key("refund-agent-delegating")  # the agent step 3 touches for agent.updated
ALERT_WAIT = int(os.environ.get("ALERT_WAIT", "0"))  # seconds to wait for the alert to tick; 0 = do not wait
MAX_BURST_TURNS = 15  # enough to pass the threshold twice over, never more
BYPASS = {"bypass-tunnel-reminder": "1"}  # localtunnel serves an HTML reminder page to clients without it


def iso(moment: datetime) -> str:
    """The timestamp format the Reporting API wants: UTC, second precision, trailing Z."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# %% [markdown]
# ## Step 1 · The number: Reporting API
#
# `POST /v2/reporting` answers "what did the last hour cost" and "who spends what" from the same
# trace data the Studio charts. `mode: scalar` aggregates the window into one row; `group_by` turns
# it into a top list. Every alert in step 2 is one of these queries on a timer.

# %%
now = datetime.now(UTC)
project_filter = [{"field": "project", "op": "eq", "values": [PROJECT]}]

cost = reporting_query(
    orq,
    metric="genai.cost",
    **{"from": iso(now - timedelta(hours=1))},  # `from` is a Python keyword, so it goes in as **kwargs
    to=iso(now),
    mode="scalar",
    filters=project_filter,
)
error_rate = reporting_query(
    orq,
    metric="genai.error_rate",
    **{"from": iso(now - timedelta(hours=1))},
    to=iso(now),
    mode="scalar",
    filters=project_filter,
)

print("── Step 1 · The number: Reporting API ─────────────────")
print(f"window   : last hour, project {settings.project}")
print(f"cost     : ${cost['data'][0]['metrics']['genai.cost']:.4f}")
print(f"errors   : rate {error_rate['data'][0]['metrics']['genai.error_rate']:.3f} (genai.error_rate)")

# %%
usage = reporting_query(
    orq,
    metric="genai.usage",
    **{"from": iso(now - timedelta(days=1))},
    to=iso(now),
    mode="scalar",
    group_by=["model"],
    filters=project_filter,
    limit=5,
)

print("top      : last 24 hours by model")
for row in usage["data"]:
    metrics = row["metrics"]
    print(
        f"    {row['dimensions']['model']:<28} requests={metrics['request_count']:<4} errors={metrics['error_count']:<3} cost=${metrics['total_cost']:.4f}"
    )
print("next     : Observability > Reporting in the Studio draws these same numbers")

# %% [markdown]
# ## Step 2 · The watcher: an alert on spend
#
# `make seed` created `ws-cost-alert`: `genai.cost > $0.002` over the last 5 minutes, checked every 5
# minutes, notifying `ws-alert-notifier` (a webhook; `WS_WEBHOOK_URL` in `.env`). An alert without
# notifiers still evaluates and records triggers. The burst below is a runaway loop in miniature:
# refund turns until the window's spend passes the threshold with margin, fifteen at most. The alert
# ticks on its own schedule and reporting ingests in minutes, so the trigger shows up 5 to 10 minutes
# later, not now: re-run with `ALERT_WAIT=600`, or check from the CLI.

# %%
notifier_id = ensure_notifier(orq)
alert_id = ensure_alert(orq, notifier_id=notifier_id)
alert = next(a for a in list_alerts() if a["alert_id"] == alert_id)
condition = alert["condition"]

print("── Step 2 · The watcher: an alert on spend ────────────")
print(f"alert    : {alert['display_name']} {alert_id}")
print(f"rule     : {alert['query']['metric']} {condition['comparator']} {condition['threshold']} over {condition['window']}, every {condition['interval']}")
print(f"status   : {alert['status']}, {len(alert['notifier_ids'])} notifier(s)")

# %%
spent = 0.0
burst: list[str] = []  # trace ids of the turns that make up the burst
while spent < 2 * ALERT_THRESHOLD_USD and len(burst) < MAX_BURST_TURNS:
    response = orq.responses.create(
        model=f"agent/{AGENT}",
        input="Explain the refund policy in about 300 words.",
        metadata={"ws_module": "14"},
    ).model_dump(by_alias=True)
    spent += response["usage"]["total_cost"]
    burst.append(response["telemetry"]["trace_id"])

print(f"burst    : {len(burst)} turns, ${spent:.4f} in the window (threshold ${condition['threshold']})")

# %%
deadline = time.time() + ALERT_WAIT
while not (triggers := alert_triggers(alert_id)) and time.time() < deadline:
    time.sleep(30)  # the alert evaluates every 5 minutes; no point polling faster

for trigger in triggers[:3]:  # newest first
    print(
        f"trigger  : {trigger['trigger_id']} {trigger['status']} {trigger['severity']} peak=${trigger['peak_value']:.4f} opened={trigger['opened_at']}"
    )
if not triggers:
    print(f"verdict  : no trigger yet (the alert checks every {condition['interval']}, reporting lags a few minutes)")
print(f"next     : orq alerts list-triggers {alert_id}; Observability > Alerts in the Studio shows the burst, the threshold line and the incident")

# %% [markdown]
# ## Step 3 · The hook: a webhook into your own system
#
# Alerts notify; webhooks stream. A workspace webhook delivers chosen events (`llm.response`,
# `llm.chat_completion`, `agent.updated`, `deployment.invoked`, ...) to an HTTPS endpoint of yours,
# signed with `X-Orq-Signature` (HMAC-SHA256 of the raw body with the webhook's secret). The
# receiver in `app/edge.py` verifies that signature and keeps what arrived, per participant
# (`POST /<prefix>`). orq cloud has to reach it: `make edge`, expose it with a tunnel (or use the
# instance the room shares), put the base URL in `WS_EDGE_URL` and the secret in
# `WS_WEBHOOK_SECRET`. Two events below: one agent call (`llm.response`) and one agent update
# (`agent.updated`).

# %%
webhook_id = ensure_webhook(orq)
webhook = orq.webhooks.get(id=webhook_id).model_dump(by_alias=True)
receiver = settings.webhook_url.rstrip("/")  # <WS_EDGE_URL>/<prefix>, or httpbin when WS_EDGE_URL is unset
edge_base = receiver.rsplit("/", 1)[0]

# Only app.edge answers /health with an `events` counter; anything else (httpbin, webhook.site)
# stores nothing we can read back.
try:
    receiver_is_ours = "events" in httpx.get(f"{edge_base}/health", headers=BYPASS, timeout=10).json()
except Exception:  # noqa: BLE001  httpbin, webhook.site, anything that is not app.edge
    receiver_is_ours = False

print("── Step 3 · The hook: a webhook into your own system ──")
print(f"webhook  : {webhook['display_name']} -> {webhook['url']}")
print(f"events   : {', '.join(webhook['events'])}")
print(f"receiver : {'app.edge' if receiver_is_ours else 'not ours (WS_EDGE_URL unset, or not app.edge)'}")

# %%
seen: set[str] = set()  # event ids already at the receiver, so we only report this run's deliveries
if receiver_is_ours:
    seen = {e["id"] for e in httpx.get(f"{receiver}/events", headers=BYPASS, timeout=20).json()["events"]}

orq.responses.create(
    model=f"agent/{AGENT}",
    input="One sentence: what is the refund window?",
    metadata={"ws_module": "14"},
)  # -> llm.response
orq.agents.update(
    agent_key=DELEGATING,
    description=f"Handles refund requests; delegates judgement and wording. [m14 webhook {int(time.time())}]",
)  # -> agent.updated

print(f"fired    : llm.response (one call to {AGENT}), agent.updated (a description touch on {DELEGATING})")

# %%
if receiver_is_ours:
    new_events: list[dict] = []
    for _ in range(6):  # deliveries usually land within 10 s, sometimes 30
        time.sleep(5)
        arrived = httpx.get(f"{receiver}/events", headers=BYPASS, timeout=20).json()["events"]
        new_events = [e for e in arrived if e["id"] not in seen]
        if len(new_events) >= 2:
            break
    for event in new_events:
        print(f"event    : {event['type']:<16} {event['id']} signature_valid={event['signature_valid']} data={json.dumps(event['data'])[:70]}")
    if not new_events:
        print("verdict  : nothing arrived in 30 s: is the tunnel up, and is WS_WEBHOOK_URL the tunnel URL? (orq retries later)")
    else:
        print(f"verdict  : {len(new_events)} deliveries, signature checked by app.edge with WS_WEBHOOK_SECRET")
    print("next     : the receiver's terminal printed the same lines as they landed; Settings > Organization > Webhooks shows the delivery metrics")
else:
    print("verdict  : deliveries are only visible in the Studio (Settings > Organization > Webhooks > Delivery metrics)")
    print("next     : make edge, expose it (npx localtunnel --port 8001), put the URL in WS_EDGE_URL and rerun to read the deliveries here")

# %% [markdown]
# ## What to take away
#
# - One trace store, three readers: the Reporting API aggregates it, an alert is one of those
#   queries on a timer, a webhook is the store calling you.
# - Alerts are project-scoped and only successful traces carry a project, so alert on cost,
#   latency or guardrail metrics, not on the error rate of requests the gateway rejected.
# - Reporting ingests in minutes, so an alert with a five-minute window fires a tick or two after
#   the burst; poll `orq alerts list-triggers` instead of waiting in the script.
# - A webhook delivery is the whole model span, signed: verify `X-Orq-Signature` before trusting
#   the body, and expect orq to switch the webhook off after ten failed deliveries.
