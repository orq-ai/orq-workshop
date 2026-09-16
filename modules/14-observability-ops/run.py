"""Module 14 starter: alerts, automations and framework hooks.

Modules 02 and 06 read traces after the fact. This module makes the platform push to you: a
Reporting API query gives the number, an alert watches it and opens an incident, and a webhook
delivers every model call, signed, to a system you run. `make seed` created `ws-alert-notifier`
and `ws-cost-alert`; your job is to query the metric the alert watches, push it over the
threshold, and fire two events into your own receiver.

Fill in the TODOs. The script runs as is; a step with an empty body prints what is missing.
Run it with `uv run python modules/14-observability-ops/run.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings
from app.refund_agent.entities import (
    ALERT_THRESHOLD_USD,
    ensure_alert,
    ensure_notifier,
    ensure_webhook,
    project_id,
    reporting_query,
)

orq = make_orq()
PROJECT = project_id(orq)
AGENT = settings.key("refund-agent")  # ws-refund-agent: its calls are attributed to the project
DELEGATING = settings.key("refund-agent-delegating")  # the agent step 3 touches for agent.updated
BYPASS = {"bypass-tunnel-reminder": "1"}  # localtunnel serves an HTML reminder page to clients without it


def iso(moment: datetime) -> str:
    """The timestamp format the Reporting API wants: UTC, second precision, trailing Z."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def step_1_reporting() -> None:
    """One scalar query for the last hour, then the same metric as a top list per model."""
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
    error_rate = None  # TODO: the same query with metric="genai.error_rate"
    usage = None  # TODO: metric="genai.usage" over the last 24 h with group_by=["model"] and limit=5 (a top list)

    print("── Step 1 · The number: Reporting API ─────────────────")
    print(f"window   : last hour, project {settings.project}")
    print(f"cost     : ${cost['data'][0]['metrics']['genai.cost']:.4f}")
    if error_rate is None or usage is None:
        print("TODO     : fill in `error_rate` and `usage`, then rerun")
    if error_rate is not None:
        print(f"errors   : rate {error_rate['data'][0]['metrics']['genai.error_rate']:.3f} (genai.error_rate)")
    if usage is not None:
        print("top      : last 24 hours by model")
        for row in usage["data"]:
            metrics = row["metrics"]
            print(
                f"    {row['dimensions']['model']:<28} requests={metrics['request_count']:<4} errors={metrics['error_count']:<3} cost=${metrics['total_cost']:.4f}"
            )
    print("next     : Observability > Reporting in the Studio draws these same numbers")


def step_2_alert() -> None:
    """Push the metric the alert watches over its threshold, then read the trigger history."""
    alert_id = ensure_alert(orq, notifier_id=ensure_notifier(orq))
    # A burst is a runaway loop in miniature: refund turns until the window's spend passes the
    # threshold with margin. The alert ticks every 5 minutes and reporting lags, so the trigger
    # shows up later, not now.
    burst: list[str] = []  # TODO: trace ids of orq.responses.create(model=f"agent/{AGENT}", input="Explain the refund policy in about 300 words.") until the summed usage.total_cost is 2 * ALERT_THRESHOLD_USD
    triggers = None  # TODO: entities.alert_triggers(alert_id), newest first (empty until the alert ticks)

    print("── Step 2 · The watcher: an alert on spend ────────────")
    print(f"alert    : {alert_id}")
    print(f"rule     : genai.cost gt {ALERT_THRESHOLD_USD} over 5m, every 5m")
    if not burst or triggers is None:
        print("TODO     : fill in `burst` and `triggers`, then rerun")
    if burst:
        print(f"burst    : {len(burst)} turns")
    for trigger in (triggers or [])[:3]:
        print(f"trigger  : {trigger['trigger_id']} {trigger['status']} {trigger['severity']} peak=${trigger['peak_value']:.4f} opened={trigger['opened_at']}")
    print(f"next     : orq alerts list-triggers {alert_id}; Observability > Alerts in the Studio shows the burst and the incident")


def step_3_webhook() -> None:
    """Create the webhook, fire one event of each subscribed kind, and ask the receiver what arrived."""
    # make edge, expose it (npx localtunnel --port 8001), WS_EDGE_URL + WS_WEBHOOK_SECRET in .env
    webhook_id = ensure_webhook(orq)
    new_events = None  # TODO: fire one llm.response (a responses.create on the agent) and one agent.updated (agents.update on DELEGATING with a new description), wait ~10 s, then GET {settings.webhook_url}/events with headers=BYPASS and keep the events that were not there before

    print("── Step 3 · The hook: a webhook into your own system ──")
    print(f"webhook  : {webhook_id} -> {settings.webhook_url}")
    if new_events is None:
        print("TODO     : fire llm.response and agent.updated, read the receiver's /events, then rerun")
    for event in new_events or []:
        print(f"event    : {event['type']:<16} {event['id']} signature_valid={event['signature_valid']}")
    print("next     : Settings > Organization > Webhooks in the Studio shows the delivery metrics")


if __name__ == "__main__":
    step_1_reporting()
    step_2_alert()
    step_3_webhook()
