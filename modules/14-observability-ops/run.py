"""Module 14 starter: alerts, automations and framework hooks.

make seed created ws-alert-notifier, ws-cost-alert and ws-review-queue. Your job: query the metric the alert
watches, push it over the threshold, route one trace into the queue, and trace a framework with one line.
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
AGENT = settings.key("refund-agent")


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def step_1_reporting() -> None:
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
    print(f"[1] cost last hour: ${cost['data'][0]['metrics']['genai.cost']:.4f}")
    # TODO: the same for genai.error_rate, then genai.usage with group_by=["model"] and limit=5 (a top list)


def step_2_alert() -> None:
    alert_id = ensure_alert(orq, notifier_id=ensure_notifier(orq))
    print(f"[2] alert {alert_id} watches genai.cost > {ALERT_THRESHOLD_USD} over 5m")
    # TODO: a burst: orq.responses.create(model=f"agent/{AGENT}", input="Explain the refund policy in about 150 words.")
    #       until the summed usage.total_cost is twice the threshold; keep the trace ids
    # TODO: entities.alert_triggers(alert_id) and print status, severity, peak_value (or the CLI command to check later)


def step_3_webhook() -> None:
    # make edge, expose it (npx localtunnel --port 8001), WS_EDGE_URL + WS_WEBHOOK_SECRET in .env
    webhook_id = ensure_webhook(orq)
    print(f"[3] webhook {webhook_id} -> {settings.webhook_url}")
    # TODO: fire one llm.response (a responses.create on the agent) and one agent.updated (agents.update on
    #       ws-refund-agent-delegating with a new description), wait ~10 s, then GET {WS_WEBHOOK_URL}/events
    #       and print type, id and signature_valid for each new event


if __name__ == "__main__":
    step_1_reporting()
    step_2_alert()
    step_3_webhook()
