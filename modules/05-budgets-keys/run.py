"""Module 05 starter: API keys, identities and budgets. Instructor demo.

Factor 5: who calls, for whom, and at what cost are request attributes the gateway enforces,
not bookkeeping the app does afterwards. Mint a key for the CI runner, tag a call with a customer
identity, budget both, watch the third call get a 429, then delete everything.

Needs a Management Key in the shell (never in .env):

    orq management-keys create --name ws-mgmt-key --permission-mode MANAGEMENT_PERMISSION_MODE_RESTRICTED \
        --access budget=ACCESS_LEVEL_WRITE --access api-key=ACCESS_LEVEL_WRITE --access management-key=ACCESS_LEVEL_WRITE -o json
    export ORQ_MANAGEMENT_KEY=<token>
    uv run python modules/05-budgets-keys/run.py

Fill in the two TODOs (the budget bodies). Without them the script still runs, creates and
deletes the key, and prints what is missing. The `try/finally` in `main()` is what deletes the
key and the budgets when a step fails: `make reset` cannot find them. Solution in solution/run.py.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import openai
from openai import OpenAI

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

IDENTITY = settings.identity_id  # customer-user_001
KEY_NAME = settings.key("ci-key")  # ws-ci-key
BUDGET_PROPAGATION_SECONDS = 5  # a new budget takes a few seconds to reach the gateway

# TODO: the identity budget: 2 requests per minute and USD 5 per month for this customer.
#       {"scope": {"identity": {"identity_external_id": IDENTITY}},
#        "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 5}, "rate_limit": {"requests_per_minute": 2}}
IDENTITY_BUDGET: dict[str, Any] = {}
# TODO: the CI key budget: a USD 1 monthly cost cap. The scope is added in main() once the key id exists.
#       {"limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 1}}
KEY_BUDGET_LIMITS: dict[str, Any] = {}

MGMT_TOKEN = os.environ.get("ORQ_MANAGEMENT_KEY", "").strip()
MGMT_HEADERS = {"Authorization": f"Bearer {MGMT_TOKEN}"}
orq = make_orq()  # the normal API key from .env


def rest(method: str, path: str, **kwargs: Any) -> httpx.Response:
    """One management-key request. REST instead of the SDK: orq_ai_sdk 4.14 trips on `_id` in these replies."""
    return httpx.request(method, f"{settings.base_url}{path}", headers=MGMT_HEADERS, timeout=30, **kwargs)


def call(client: OpenAI, text: str, **kwargs: Any) -> str:
    """One cheap router call through `client`. A 429 comes back as text with its error body, not as an exception."""
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=settings.model,
            messages=[{"role": "user", "content": text}],
            **kwargs,
        )
        return f"HTTP {raw.status_code}"
    except openai.APIStatusError as error:
        return f"HTTP {error.status_code}, the budget error body:\n{json.dumps(error.body, indent=2)}"


def main() -> None:
    # ── Step 2 · Identities ──
    # The identity is the customer the call is made for. It needs only the normal key, so it
    # runs first; the management key is needed from step 1 (the API key) onwards.
    found = [
        identity
        for identity in (orq.identities.list(limit=100, search=IDENTITY).data or [])
        if identity.external_id == IDENTITY
    ]
    if found:
        identity = found[0]
    else:
        identity = orq.identities.create(external_id=IDENTITY, display_name="Workshop customer user_001")
    print("── Step 2 · Identities ────────────────────────────────")
    print(f"identity : {IDENTITY} id {identity.id}")
    print(f"next     : orq identities list --search {IDENTITY}")

    # ── Step 4a · The .env key on /v2/budgets ──
    # A normal API key calls models and reads traces; budgets are a management-key job.
    print("── Step 4a · The .env key on /v2/budgets ──────────────")
    try:
        orq.budgets.list(limit=5)
        print("api key  : listed budgets (unexpected: the .env key should get a 403)")
    except Exception as error:  # noqa: BLE001  the SDK wraps the 403 in its own error type; the body is the point
        print(f"api key  : {str(error)[:80]}")
    if not MGMT_TOKEN:
        print("next     : set ORQ_MANAGEMENT_KEY (see the docstring) to run the key and budget steps")
        return

    # ── Step 1 · A key for the CI runner ──
    # Restricted mode with three access levels: call models, read datasets and evaluators.
    # The token is returned once, in this response; the list endpoint never shows it.
    response = rest(
        "POST",
        "/v2/api-keys",
        json={
            "name": KEY_NAME,
            "permission_mode": "PERMISSION_MODE_RESTRICTED",
            "access": {
                "chat_completions": "ACCESS_LEVEL_WRITE",
                "dataset": "ACCESS_LEVEL_READ",
                "eval": "ACCESS_LEVEL_READ",
            },
        },
    )
    response.raise_for_status()
    created = response.json()
    record = created.get("api_key", created)
    api_key_id = record["id"]
    token = created.get("token") or record["token"]
    print("── Step 1 · A key for the CI runner ───────────────────")
    print(f"created  : {KEY_NAME} id={api_key_id} (token kept in memory only)")
    print(f"stored   : permission_mode={record.get('permission_mode')} project_scope={record.get('project_scope')}")
    ci_client = OpenAI(api_key=token, base_url=settings.router_url, timeout=60, max_retries=0)
    budget_ids: list[str] = []
    try:
        # ── Step 3a · Identity budget: the third call fails ──
        # Three tagged calls inside one minute against a 2 rpm budget: the third is a 429 whose
        # body names the budget (`scope_kind`, `scope_target_id`) and the dimension.
        print("── Step 3a · Identity budget: the third call fails ────")
        if IDENTITY_BUDGET:
            created = rest("POST", "/v2/budgets", json=IDENTITY_BUDGET).json()
            budget = created.get("budget", created)
            budget_ids.append(budget["budgetId"])
            print(f"budget   : {budget['budgetId']} match={budget.get('match')}")
            time.sleep(BUDGET_PROPAGATION_SECONDS)
            for i in (1, 2, 3):
                print(f"call {i}   : {call(ci_client, f'say ok #{i}', extra_headers={'X-ORQ-IDENTITY-ID': IDENTITY})}")
            print("next     : switch on `code` in the error body: requests_per_minute_exceeded is this budget")
        else:
            print("TODO     : fill in IDENTITY_BUDGET at the top of the file, then rerun")

        # ── Step 3b · API key budget: a cost cap for CI ──
        print("── Step 3b · API key budget: a cost cap for CI ────────")
        if KEY_BUDGET_LIMITS:
            created = rest(
                "POST",
                "/v2/budgets",
                json={"scope": {"api_key": {"api_key_id": api_key_id}}, **KEY_BUDGET_LIMITS},
            ).json()
            budget = created.get("budget", created)
            budget_ids.append(budget["budgetId"])
            print(f"budget   : {budget['budgetId']} match={budget.get('match')}")
            print("next     : a call through ws-ci-key now returns x-ratelimit-remaining-cost")
        else:
            print("TODO     : fill in KEY_BUDGET_LIMITS at the top of the file, then rerun")

        # ── Step 4b · The management key on /v2/budgets ──
        budgets = rest("GET", "/v2/budgets", params={"limit": 100}).json().get("data", [])
        print("── Step 4b · The management key on /v2/budgets ────────")
        print(f"mgmt key : {len(budgets)} budgets")
        print("next     : ORQ_API_KEY=$ORQ_MANAGEMENT_KEY orq budgets list -o json shows the same")
    finally:
        # ── Step 5 · Cleanup ──
        # Runs even when a step above failed: this is the only thing that deletes the key and
        # the budgets. The management key cannot delete itself; the CLI session can.
        print("── Step 5 · Cleanup ───────────────────────────────────")
        for budget_id in budget_ids:
            print(f"budget   : {budget_id} deleted, HTTP {rest('DELETE', '/v2/budgets/' + budget_id).status_code}")
        print(f"api key  : {api_key_id} deleted, HTTP {rest('DELETE', '/v2/api-keys/' + api_key_id).status_code}")
        print("next     : orq management-keys delete <id> --force, then unset ORQ_MANAGEMENT_KEY")


if __name__ == "__main__":
    main()
