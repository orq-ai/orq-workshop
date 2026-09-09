"""Module 05 starter: API keys, identities and budgets. Instructor demo.

Factor 5: who calls, for whom, and at what cost are request attributes the gateway enforces.

    orq management-keys create --name ws-mgmt-key --permission-mode MANAGEMENT_PERMISSION_MODE_RESTRICTED \
        --access budget=ACCESS_LEVEL_WRITE --access api-key=ACCESS_LEVEL_WRITE --access management-key=ACCESS_LEVEL_WRITE --json
    export ORQ_MANAGEMENT_KEY=<token>
    uv run python modules/05-budgets-keys/run.py

Fill in the TODOs. Without them the script still runs and only lists what it can.
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

IDENTITY = settings.identity_id                       # customer-user_001
KEY_NAME = settings.key("ci-key")
# TODO: {"scope": {"identity": {"identity_external_id": IDENTITY}}, "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 5}, "rate_limit": {"requests_per_minute": 2}}
IDENTITY_BUDGET: dict[str, Any] = {}
# TODO: {"scope": {"api_key": {"api_key_id": <kid>}}, "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 1}}
KEY_BUDGET_LIMITS: dict[str, Any] = {}

MGMT_TOKEN = os.environ.get("ORQ_MANAGEMENT_KEY", "").strip()
MGMT = {"Authorization": f"Bearer {MGMT_TOKEN}"}
orq = make_orq()


def rest(method: str, path: str, **kw: Any) -> httpx.Response:
    return httpx.request(method, f"{settings.base_url}{path}", headers=MGMT, timeout=30, **kw)


def call(client: OpenAI, text: str, **kw: Any) -> str:
    try:
        raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[{"role": "user", "content": text}], **kw)
        return f"{raw.status_code}"
    except openai.APIStatusError as e:
        return f"{e.status_code} {json.dumps(e.body)}"


def main() -> None:
    found = [i for i in (orq.identities.list(limit=100, search=IDENTITY).data or []) if i.external_id == IDENTITY]
    ident = found[0] if found else orq.identities.create(external_id=IDENTITY, display_name="Workshop customer user_001")
    print(f"[2] identity {ident.id} external_id={IDENTITY}")
    try:
        orq.budgets.list(limit=5)
    except Exception as e:
        print(f"[4] normal key on /v2/budgets: {str(e)[:80]}")
    if not MGMT_TOKEN:
        print("set ORQ_MANAGEMENT_KEY (see the docstring) to run the key and budget steps")
        return

    r = rest("POST", "/v2/api-keys", json={"name": KEY_NAME, "permission_mode": "PERMISSION_MODE_RESTRICTED",
                                            "access": {"chat_completions": "ACCESS_LEVEL_WRITE", "dataset": "ACCESS_LEVEL_READ", "eval": "ACCESS_LEVEL_READ"}})
    r.raise_for_status()
    created = r.json(); rec = created.get("api_key", created); kid, token = rec["id"], created.get("token") or rec["token"]
    print(f"[1] created {KEY_NAME} id={kid} (token kept in memory)")
    ci = OpenAI(api_key=token, base_url=settings.router_url, timeout=60, max_retries=0)
    budgets: list[str] = []
    try:
        if IDENTITY_BUDGET:
            b = rest("POST", "/v2/budgets", json=IDENTITY_BUDGET).json(); b = b.get("budget", b); budgets.append(b["budgetId"])
            print(f"[3a] identity budget {b['budgetId']} match={b.get('match')}")
            time.sleep(5)
            for i in (1, 2, 3):
                print(f"[3a] call {i}: {call(ci, f'say ok #{i}', extra_headers={'X-ORQ-IDENTITY-ID': IDENTITY})}")
        else:
            print("[3a] TODO: fill IDENTITY_BUDGET")
        if KEY_BUDGET_LIMITS:
            b = rest("POST", "/v2/budgets", json={"scope": {"api_key": {"api_key_id": kid}}, **KEY_BUDGET_LIMITS}).json(); b = b.get("budget", b); budgets.append(b["budgetId"])
            print(f"[3b] api-key budget {b['budgetId']} match={b.get('match')}")
        else:
            print("[3b] TODO: fill KEY_BUDGET_LIMITS")
        print(f"[4] management key lists {len(rest('GET', '/v2/budgets', params={'limit': 100}).json().get('data', []))} budgets")
    finally:
        for b in budgets:
            print(f"[5] delete budget {b}: {rest('DELETE', '/v2/budgets/' + b).status_code}")
        print(f"[5] delete api key {kid}: {rest('DELETE', '/v2/api-keys/' + kid).status_code}")
        print("[5] then: orq management-keys delete <id> --force; unset ORQ_MANAGEMENT_KEY")


if __name__ == "__main__":
    main()
