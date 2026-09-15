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

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import (
    ALERT_THRESHOLD_USD,
    alert_triggers,
    ensure_alert,
    ensure_notifier,
    list_alerts,
    project_id,
    reporting_query,
)

orq = make_orq()
PROJECT = project_id(orq)
AGENT = settings.key("refund-agent")  # ws-refund-agent: its calls are attributed to the project
ALERT_WAIT = int(
    os.environ.get("ALERT_WAIT", "0")
)  # seconds to wait for the alert to tick; 0 = do not wait


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    **{"from": iso(now - timedelta(hours=1))},
    to=iso(now),
    mode="scalar",
    filters=project_filter,
)
rate = reporting_query(
    orq,
    metric="genai.error_rate",
    **{"from": iso(now - timedelta(hours=1))},
    to=iso(now),
    mode="scalar",
    filters=project_filter,
)
print(
    f"[1] last hour, project {settings.project}: cost=${cost['data'][0]['metrics']['genai.cost']:.4f} error_rate={rate['data'][0]['metrics']['genai.error_rate']:.3f}"
)
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
for row in usage["data"]:
    m = row["metrics"]
    print(
        f"    {row['dimensions']['model']:<28} requests={m['request_count']:<4} errors={m['error_count']:<3} cost=${m['total_cost']:.4f}"
    )

# %% [markdown]
# ## Step 2 · The watcher: an alert on spend
#
# `make seed` created `ws-cost-alert`: `genai.cost > $0.002` over the last 5 minutes, checked every 5
# minutes, notifying `ws-alert-notifier` (a webhook; `WS_WEBHOOK_URL` in `.env`). An alert without
# notifiers still evaluates and records triggers. The burst below is a runaway loop in miniature:
# refund turns until the window's spend passes the threshold with margin, fifteen at most. The alert ticks on its own schedule
# and reporting ingests in minutes, so the trigger shows up 5 to 10 minutes later, not now:
# re-run with `ALERT_WAIT=600`, or check from the CLI.

# %%
notifier = ensure_notifier(orq)
alert_id = ensure_alert(orq, notifier_id=notifier)
alert = next(a for a in list_alerts() if a["alert_id"] == alert_id)
c = alert["condition"]
print(
    f"[2] alert {alert['display_name']} {alert_id}: {alert['query']['metric']} {c['comparator']} {c['threshold']} over {c['window']}, every {c['interval']}, status={alert['status']} notifiers={len(alert['notifier_ids'])}"
)
spent, burst = 0.0, []
while spent < 2 * ALERT_THRESHOLD_USD and len(burst) < 15:
    r = orq.responses.create(
        model=f"agent/{AGENT}",
        input="Explain the refund policy in about 300 words.",
        metadata={"ws_module": "14"},
    ).model_dump(by_alias=True)
    spent += r["usage"]["total_cost"]
    burst.append(r["telemetry"]["trace_id"])
print(f"    burst: {len(burst)} turns, ${spent:.4f} in the window (threshold ${c['threshold']})")
deadline = time.time() + ALERT_WAIT
while not (triggers := alert_triggers(alert_id)) and time.time() < deadline:
    time.sleep(30)
for t in triggers[:3]:
    print(
        f"    trigger {t['trigger_id']} status={t['status']} severity={t['severity']} peak=${t['peak_value']:.4f} opened={t['opened_at']}"
    )
if not triggers:
    print(
        f"    no trigger yet (the alert checks every {c['interval']}, reporting lags a few minutes); run: orq alerts list-triggers {alert_id}"
    )

# %% [markdown]
# ## Step 3 · The hook: a webhook into your own system
#
# Alerts notify; webhooks stream. A workspace webhook delivers chosen events (`llm.response`,
# `llm.chat_completion`, `agent.updated`, `deployment.invoked`, ...) to an HTTPS endpoint of yours,
# signed with `X-Orq-Signature` (HMAC-SHA256 of the raw body with the webhook's secret). The
# receiver in `app/edge.py` verifies that signature and keeps what arrived, per participant
# (`POST /<prefix>`). orq cloud has to reach it: `make edge`, expose it with a tunnel (or use the
# instance the room shares), put the base URL in `WS_EDGE_URL` and the secret in `WS_WEBHOOK_SECRET`. Two events below: one agent call
# (`llm.response`) and one agent update (`agent.updated`).

# %%
import httpx

from app.refund_agent.entities import ensure_webhook

DELEGATING = settings.key("refund-agent-delegating")  # the agent we touch for agent.updated
webhook_id = ensure_webhook(orq)
w = orq.webhooks.get(id=webhook_id).model_dump(by_alias=True)
receiver = settings.webhook_url.rstrip("/")
BYPASS = {"bypass-tunnel-reminder": "1"}  # localtunnel serves an HTML reminder page to clients without it
try:
    ours = "events" in httpx.get(f"{receiver.rsplit('/', 1)[0]}/health", headers=BYPASS, timeout=10).json()
except Exception:  # noqa: BLE001  httpbin, webhook.site, anything that is not app.edge
    ours = False
print(
    f"[3] webhook {w['display_name']} -> {w['url']} events={w['events']} receiver={'app.edge' if ours else 'not ours'}"
)
seen = {e["id"] for e in httpx.get(f"{receiver}/events", headers=BYPASS, timeout=20).json()["events"]} if ours else set()
orq.responses.create(
    model=f"agent/{AGENT}",
    input="One sentence: what is the refund window?",
    metadata={"ws_module": "14"},
)  # -> llm.response
orq.agents.update(
    agent_key=DELEGATING,
    description=f"Handles refund requests; delegates judgement and wording. [m14 webhook {int(time.time())}]",
)  # -> agent.updated
if ours:
    new: list[dict] = []
    for _ in range(6):  # deliveries usually land within 10 s, sometimes 30
        time.sleep(5)
        new = [e for e in httpx.get(f"{receiver}/events", headers=BYPASS, timeout=20).json()["events"] if e["id"] not in seen]
        if len(new) >= 2:
            break
    for e in new:
        print(
            f"    {e['type']:<16} {e['id']} signature_valid={e['signature_valid']} data={json.dumps(e['data'])[:70]}"
        )
    if not new:
        print(
            "    nothing arrived in 30 s: is the tunnel up, and is WS_WEBHOOK_URL the tunnel URL? (orq retries later)"
        )
else:
    print(
        "    deliveries are only visible in the Studio (Settings > Organization > Webhooks > Delivery metrics); point WS_EDGE_URL at app.edge to read them here"
    )
