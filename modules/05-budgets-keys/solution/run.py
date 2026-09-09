"""Module 05 solution: API keys, identities and budgets. Instructor demo.

Factor 5: unify execution state and business state. Who called, on whose behalf, and what it may
cost are request attributes the gateway enforces, not bookkeeping the app does afterwards.

Needs a Management Key in the shell (never in .env):

    orq management-keys create --name ws-mgmt-key --permission-mode MANAGEMENT_PERMISSION_MODE_RESTRICTED \
        --access budget=ACCESS_LEVEL_WRITE --access api-key=ACCESS_LEVEL_WRITE --access management-key=ACCESS_LEVEL_WRITE --json
    export ORQ_MANAGEMENT_KEY=<token from the response>
    uv run python modules/05-budgets-keys/solution/run.py

Every entity this run creates is deleted at the end: two budgets, the API key, the management key.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx
import openai
from openai import OpenAI
from orq_ai_sdk import Orq

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

MGMT_TOKEN = os.environ.get("ORQ_MANAGEMENT_KEY", "").strip()
if not MGMT_TOKEN:
    raise SystemExit("ORQ_MANAGEMENT_KEY is not set. Create one with `orq management-keys create` and export it in this shell only.")

MGMT = {"Authorization": f"Bearer {MGMT_TOKEN}"}
KEY_NAME = settings.key("ci-key")
MGMT_KEY_NAME = settings.key("mgmt-key")
IDENTITY = settings.identity_id  # customer-user_001

orq = make_orq()                                            # the normal key from .env
mgmt = Orq(api_key=MGMT_TOKEN, server_url=settings.base_url)  # the management key, budgets and keys only


# ---------------------------------------------------------------- helpers (REST where the SDK 4.14 trips on `_id`)

def get(path: str, headers: dict[str, str] = MGMT, **params: Any) -> Any:
    r = httpx.get(f"{settings.base_url}{path}", headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict[str, Any], headers: dict[str, str] = MGMT) -> dict[str, Any]:
    r = httpx.post(f"{settings.base_url}{path}", headers=headers, json=body, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def delete(path: str, headers: dict[str, str] = MGMT) -> int:
    return httpx.delete(f"{settings.base_url}{path}", headers=headers, timeout=30).status_code


def project_id() -> str:
    for p in orq.projects.list(limit=100).data or []:
        d = p.model_dump()
        if settings.project in (d.get("name"), d.get("key")):
            return d.get("project_id") or d.get("id")
    raise SystemExit(f"project {settings.project} not found")


def list_budgets() -> list[dict[str, Any]]:
    return get("/v2/budgets", limit=100).get("data", [])


def budget_id(b: dict[str, Any]) -> str:
    return b.get("budgetId") or b.get("budget_id") or b.get("_id") or b.get("id")


def call(client: OpenAI, text: str, **kw: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
    """One cheap router call. Returns (status, body-or-error, interesting headers)."""
    try:
        raw = client.chat.completions.with_raw_response.create(model=settings.model, messages=[{"role": "user", "content": text}], **kw)
        h = {k: v for k, v in raw.headers.items() if k.lower().startswith("x-ratelimit") or k.lower() == "x-orq-trace-id"}
        return raw.status_code, {"answer": raw.parse().choices[0].message.content}, h
    except openai.APIStatusError as e:
        h = {k: v for k, v in e.response.headers.items() if k.lower().startswith("x-ratelimit") or k.lower() in ("retry-after", "x-orq-trace-id")}
        return e.status_code, e.body if isinstance(e.body, dict) else {"message": str(e.body)}, h


# ---------------------------------------------------------------- steps

def step_1_api_key() -> tuple[str, str]:
    keys = get("/v2/api-keys", limit=200)
    keys = keys.get("data", keys) if isinstance(keys, dict) else keys
    print(f"[1] api keys in workspace: {len(keys)} (list never returns a token)")
    for k in keys:
        if k["name"] == KEY_NAME:  # a previous run died before cleanup; the token is gone, so recreate
            print(f"[1] stale {KEY_NAME} {k['id']} deleted: {delete('/v2/api-keys/' + k['id'])}")
    created = post("/v2/api-keys", {
        "name": KEY_NAME,
        "project_scope": {"mode": "single", "project_id": project_id()},
        "permission_mode": "PERMISSION_MODE_RESTRICTED",
        "access": {"chat_completions": "ACCESS_LEVEL_WRITE", "dataset": "ACCESS_LEVEL_READ", "eval": "ACCESS_LEVEL_READ"},
    })
    rec = created.get("api_key", created)
    token = created.get("token") or rec.get("token")
    kid = rec["id"]
    stored = get(f"/v2/api-keys/{kid}")
    stored = stored.get("api_key", stored)
    print(f"[1] created {KEY_NAME} id={kid} token=sk-orq-...{token[-4:]} (kept in memory only)")
    print(f"[1] stored  permission_mode={stored.get('permission_mode')} project_scope={stored.get('project_scope')} access={stored.get('access')} family={stored.get('legacy_token_family')}")
    return kid, token


def step_2_identity(ci: OpenAI) -> None:
    found = [i for i in (orq.identities.list(limit=100, search=IDENTITY).data or []) if i.external_id == IDENTITY]
    if found:
        print(f"[2] identity exists {found[0].id} external_id={IDENTITY}")
    else:
        i = orq.identities.create(external_id=IDENTITY, display_name="Workshop customer user_001")
        print(f"[2] identity created {i.id} external_id={IDENTITY}")
    # X-ORQ-IDENTITY-ID is read on every gateway request; `orq.identity.id` in the body did not attribute in 4.14
    status, body, h = call(ci, "say ok", extra_headers={"X-ORQ-IDENTITY-ID": IDENTITY})
    print(f"[2] tagged call {status} trace={h.get('x-orq-trace-id')}  (orq identities list --search {IDENTITY})")


def step_3_budgets(ci: OpenAI, kid: str) -> list[str]:
    ids: list[str] = []
    existing = {json.dumps(b.get("scope"), sort_keys=True): b for b in list_budgets()}

    # (a) identity budget: 2 requests per minute and USD 5 per month for this customer
    scope = {"identity": {"identity_external_id": IDENTITY}}
    b = existing.get(json.dumps({"identity": {"identityExternalId": IDENTITY}}, sort_keys=True))
    if b is None:
        b = post("/v2/budgets", {"scope": scope, "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 5}, "rate_limit": {"requests_per_minute": 2}})
        b = b.get("budget", b)
    ids.append(budget_id(b))
    print(f"[3a] identity budget {ids[-1]} match={b.get('match')} limits={b.get('limits')} rate_limit={b.get('rateLimit') or b.get('rate_limit')}")
    time.sleep(5)
    for i in (1, 2, 3):
        status, body, h = call(ci, f"say ok #{i}", extra_headers={"X-ORQ-IDENTITY-ID": IDENTITY})
        if status == 200:
            print(f"[3a] call {i}: {status}")
        else:
            print(f"[3a] call {i}: {status} {json.dumps(body)}")
            print(f"     headers: {h}")
    usage = get(f"/v2/budgets/{ids[-1]}")
    print(f"[3a] usage after: {(usage.get('budget') or usage).get('usage')}")

    # (b) API key budget: a cost cap for the CI runner
    scope = {"api_key": {"api_key_id": kid}}
    b = post("/v2/budgets", {"scope": scope, "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 1}})
    b = b.get("budget", b)
    ids.append(budget_id(b))
    print(f"[3b] api-key budget {ids[-1]} match={b.get('match')} limits={b.get('limits')}")
    time.sleep(5)
    status, body, h = call(ci, "say ok")  # no identity header: only the key budget applies
    cost_headers = {k: v for k, v in h.items() if "cost" in k}
    print(f"[3b] call with {KEY_NAME}: {status} cost headers={cost_headers}")
    return ids


def step_4_who_may_list() -> None:
    rows = [(budget_id(b), list(b["scope"].keys())[0], b.get("limits"), (b.get("rateLimit") or b.get("rate_limit")), b.get("usage")) for b in list_budgets()]
    print(f"[4] management key: {len(rows)} budgets")
    for r in rows:
        print(f"     {r[0]} scope={r[1]} limits={r[2]} rate_limit={r[3]} usage={r[4]}")
    try:
        orq.budgets.list(limit=5)
        print("[4] normal key: listed budgets (unexpected)")
    except Exception as e:
        print(f"[4] normal key: {type(e).__name__} {str(e)[:110]}")


def step_5_cleanup(budget_ids: list[str], kid: str) -> None:
    for b in budget_ids:
        print(f"[5] delete budget {b}: {delete('/v2/budgets/' + b)}")
    print(f"[5] delete api key {kid}: {delete('/v2/api-keys/' + kid)}")
    # the token does not embed the key id, so find the management key by its name
    me = [k for k in get("/v2/management-keys", limit=100).get("data", []) if k.get("name") == MGMT_KEY_NAME]
    for k in me:
        mid = k.get("management_key_id") or k.get("id")
        r = httpx.delete(f"{settings.base_url}/v2/management-keys/{mid}", headers=MGMT, timeout=30)
        if r.status_code < 300:
            print(f"[5] delete management key {mid}: {r.status_code}")
        else:  # a management key cannot delete itself; the CLI session can
            print(f"[5] delete management key {mid}: {r.status_code} {r.json().get('message')}")
            print(f"    run: orq management-keys delete {mid} --force")
    print("[5] then: unset ORQ_MANAGEMENT_KEY. `make reset` has nothing to do for this module.")


if __name__ == "__main__":
    kid, token = step_1_api_key()
    ci = OpenAI(api_key=token, base_url=settings.router_url, timeout=60, max_retries=0)
    budgets: list[str] = []
    try:
        step_2_identity(ci)
        budgets = step_3_budgets(ci, kid)
        step_4_who_may_list()
    finally:
        step_5_cleanup(budgets, kid)
