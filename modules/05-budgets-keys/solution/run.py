"""Module 05 solution: API keys, identities and budgets. Instructor demo.

Factor 5: unify execution state and business state. Who called, on whose behalf, and what it may
cost are request attributes the gateway enforces, not bookkeeping the app does afterwards. Five
steps: mint a restricted API key for the CI runner, tag a call with a customer identity, put a
budget on that identity and one on the key and watch the third call come back as a 429, compare
what each credential may list, then delete everything again.

Needs a Management Key in the shell (never in .env):

    orq management-keys create --name ws-mgmt-key --permission-mode MANAGEMENT_PERMISSION_MODE_RESTRICTED \
        --access budget=ACCESS_LEVEL_WRITE --access api-key=ACCESS_LEVEL_WRITE --access management-key=ACCESS_LEVEL_WRITE -o json
    export ORQ_MANAGEMENT_KEY=<token from the response>
    uv run python modules/05-budgets-keys/solution/run.py

This stays a plain script on purpose: the `try/finally` in `__main__` is the only thing that
deletes the API key and the budgets when a step fails half way. `make reset` cannot find them,
because keys and budgets carry no `ws-` path. Every entity this run creates is deleted at the end:
two budgets, the API key, and (from the CLI) the management key.
"""

from __future__ import annotations

import json
import os
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
    raise SystemExit(
        "ORQ_MANAGEMENT_KEY is not set. Create one with `orq management-keys create` "
        "and export it in this shell only."
    )

MGMT_HEADERS = {"Authorization": f"Bearer {MGMT_TOKEN}"}
KEY_NAME = settings.key("ci-key")  # ws-ci-key
MGMT_KEY_NAME = settings.key("mgmt-key")  # ws-mgmt-key, the name used in the docstring command
IDENTITY = settings.identity_id  # customer-user_001
BUDGET_PROPAGATION_SECONDS = 5  # a new budget takes a few seconds to reach the gateway
CI_KEY_REQUEST = {
    "name": KEY_NAME,
    "permission_mode": "PERMISSION_MODE_RESTRICTED",
    "access": {
        "chat_completions": "ACCESS_LEVEL_WRITE",
        "dataset": "ACCESS_LEVEL_READ",
        "eval": "ACCESS_LEVEL_READ",
    },
}

orq = make_orq()  # the normal API key from .env: identities, traces, models
mgmt = Orq(api_key=MGMT_TOKEN, server_url=settings.base_url)  # the management key: budgets and keys only


# ── Helpers ────────────────────────────────────────────────────────────────────────────────────
# REST instead of the SDK for keys and budgets: orq_ai_sdk 4.14 trips on `_id` in these
# responses (`mgmt.budgets.list()` fails on an empty list because `data` is missing, and
# `api_keys.create()` rejects the documented `single` project scope). Three thin wrappers over
# httpx keep the calls readable; the management headers are the default.


def get(path: str, headers: dict[str, str] = MGMT_HEADERS, **params: Any) -> Any:
    """GET a management endpoint and return the JSON body; raises on any 4xx/5xx."""
    response = httpx.get(f"{settings.base_url}{path}", headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def post(path: str, body: dict[str, Any], headers: dict[str, str] = MGMT_HEADERS) -> dict[str, Any]:
    """POST a JSON body; raises with the first 300 chars of the reply on anything but 2xx."""
    response = httpx.post(f"{settings.base_url}{path}", headers=headers, json=body, timeout=30)
    if response.status_code >= 300:
        raise RuntimeError(f"POST {path} -> {response.status_code}: {response.text[:300]}")
    return response.json()


def delete(path: str, headers: dict[str, str] = MGMT_HEADERS) -> int:
    """DELETE and return the status code only: cleanup must never raise."""
    return httpx.delete(f"{settings.base_url}{path}", headers=headers, timeout=30).status_code


def project_id() -> str:
    """Id of the workshop project, matched by name or key; single-project keys need it."""
    for project in orq.projects.list(limit=100).data or []:
        record = project.model_dump()
        if settings.project in (record.get("name"), record.get("key")):
            return record.get("project_id") or record.get("id")
    raise SystemExit(f"project {settings.project} not found")


def list_budgets() -> list[dict[str, Any]]:
    """Every budget the management key can see; `data` is missing when there are none."""
    return get("/v2/budgets", limit=100).get("data", [])


def budget_id(budget: dict[str, Any]) -> str:
    """The id field has been spelled four ways across API versions: read whichever is present."""
    return budget.get("budgetId") or budget.get("budget_id") or budget.get("_id") or budget.get("id")


def call(client: OpenAI, text: str, **kwargs: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
    """One cheap router call through `client`.

    Returns (status, body-or-error-body, interesting headers) so that a 429 is data to print,
    not an exception to catch. The headers kept are the rate-limit ones and the trace id.
    """
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=settings.model,
            messages=[{"role": "user", "content": text}],
            **kwargs,
        )
        headers = {
            name: value
            for name, value in raw.headers.items()
            if name.lower().startswith("x-ratelimit") or name.lower() == "x-orq-trace-id"
        }
        return raw.status_code, {"answer": raw.parse().choices[0].message.content}, headers
    except openai.APIStatusError as error:
        headers = {
            name: value
            for name, value in error.response.headers.items()
            if name.lower().startswith("x-ratelimit")
            or name.lower() in ("retry-after", "x-orq-trace-id")
        }
        body = error.body if isinstance(error.body, dict) else {"message": str(error.body)}
        return error.status_code, body, headers


# ── Step 1 · A key for the CI runner ───────────────────────────────────────────────────────────
# A CI runner that runs `make eval` needs to call models and read datasets and evaluators,
# nothing else. Ask for exactly that: single project, restricted mode, three access levels. The
# token comes back once, in the create response; the list endpoint never returns it.


def step_1_api_key() -> tuple[str, str]:
    """Mint `ws-ci-key`, deleting a stale one first. Returns (api_key_id, token)."""
    listed = get("/v2/api-keys", limit=200)
    keys = listed.get("data", listed) if isinstance(listed, dict) else listed

    print("── Step 1 · A key for the CI runner ───────────────────")
    print(f"existing : {len(keys)} api keys in the workspace (list never returns a token)")
    for key in keys:
        if key["name"] == KEY_NAME:  # a previous run died before cleanup; the token is gone, so recreate
            print(f"stale    : {KEY_NAME} {key['id']} deleted, HTTP {delete('/v2/api-keys/' + key['id'])}")

    created = post(
        "/v2/api-keys",
        {**CI_KEY_REQUEST, "project_scope": {"mode": "single", "project_id": project_id()}},
    )
    record = created.get("api_key", created)
    token = created.get("token") or record.get("token")
    api_key_id = record["id"]
    stored = get(f"/v2/api-keys/{api_key_id}")
    stored = stored.get("api_key", stored)

    print(f"created  : {KEY_NAME} id={api_key_id} token=sk-orq-…{token[-4:]} (kept in memory only)")
    print("asked    : permission_mode=PERMISSION_MODE_RESTRICTED project_scope=single access=chat_completions:write, dataset:read, eval:read")
    print(f"stored   : permission_mode={stored.get('permission_mode')} project_scope={stored.get('project_scope')} access={stored.get('access')} family={stored.get('legacy_token_family')}")
    print("next     : compare `asked` with `stored`; where the API kept `all`, the budget in step 3 is the real limit on this key")
    return api_key_id, token


# ── Step 2 · Identities ────────────────────────────────────────────────────────────────────────
# An identity is the customer the call is made for. Create it once, then tag every call with
# the `X-ORQ-IDENTITY-ID` header: traces group under it and identity budgets count it.


def step_2_identity(ci_client: OpenAI) -> None:
    """Create `customer-user_001` if missing, then make one tagged call through the CI key."""
    found = [
        identity
        for identity in (orq.identities.list(limit=100, search=IDENTITY).data or [])
        if identity.external_id == IDENTITY
    ]
    if found:
        identity_id = found[0].id
        state = "exists"
    else:
        identity_id = orq.identities.create(
            external_id=IDENTITY, display_name="Workshop customer user_001"
        ).id
        state = "created"

    # X-ORQ-IDENTITY-ID is read on every gateway request; `orq.identity.id` in the body did not
    # attribute the call to the identity in 4.14 (neither for budgets nor for the trace).
    status, _body, headers = call(ci_client, "say ok", extra_headers={"X-ORQ-IDENTITY-ID": IDENTITY})

    print("── Step 2 · Identities ────────────────────────────────")
    print(f"identity : {IDENTITY} {state}, id {identity_id}")
    print(f"call     : HTTP {status} through {KEY_NAME} with header X-ORQ-IDENTITY-ID: {IDENTITY}")
    print(f"trace    : {headers.get('x-orq-trace-id')}")
    print(f"next     : orq identities list --search {IDENTITY}; in Traces, filter by identity {IDENTITY}")


# ── Step 3 · Budgets: the third call fails ─────────────────────────────────────────────────────
# Two budgets. (a) On the identity: 2 requests per minute and USD 5 per month, so the third
# tagged call inside a minute is a 429 whose body names the budget and the dimension. (b) On the
# CI key: a USD 1 monthly cost cap; the response headers then carry the remaining capacity.


def step_3_budgets(ci_client: OpenAI, api_key_id: str) -> list[str]:
    """Create (or reuse) the identity budget and create the key budget. Returns both ids."""
    budget_ids: list[str] = []
    existing = {json.dumps(budget.get("scope"), sort_keys=True): budget for budget in list_budgets()}

    # (a) identity budget: reuse one from a run that died before cleanup, else create it.
    # The API echoes scopes in camelCase, so the lookup key is spelled the way the list returns it.
    scope = {"identity": {"identity_external_id": IDENTITY}}
    budget = existing.get(json.dumps({"identity": {"identityExternalId": IDENTITY}}, sort_keys=True))
    state = "reused"
    if budget is None:
        created = post(
            "/v2/budgets",
            {
                "scope": scope,
                "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 5},
                "rate_limit": {"requests_per_minute": 2},
            },
        )
        budget = created.get("budget", created)
        state = "created"
    budget_ids.append(budget_id(budget))

    print("── Step 3a · Identity budget: the third call fails ────")
    print(f"budget   : {budget_ids[-1]} ({state}) match={budget.get('match')}")
    print(f"limits   : {budget.get('limits')} rate_limit={budget.get('rateLimit') or budget.get('rate_limit')}")
    time.sleep(BUDGET_PROPAGATION_SECONDS)
    for i in (1, 2, 3):
        status, body, headers = call(
            ci_client, f"say ok #{i}", extra_headers={"X-ORQ-IDENTITY-ID": IDENTITY}
        )
        if status == 200:
            print(f"call {i}   : HTTP {status}")
        else:
            # The error body is the lesson: `code` is what your code switches on, `scope_kind`
            # and `scope_target_id` say which budget fired, `dimension` says which limit.
            print(f"call {i}   : HTTP {status}, the budget error body:")
            print(json.dumps(body, indent=2))
            print(f"headers  : {headers}")
    usage = get(f"/v2/budgets/{budget_ids[-1]}")
    print(f"usage    : {(usage.get('budget') or usage).get('usage')}")
    print("next     : switch on `code` (requests_per_minute_exceeded, cost_budget_exceeded, token_budget_exceeded); plain rate_limit_exceeded is the platform limit, not a budget")

    # (b) API key budget: a cost cap for the CI runner, always created fresh (the key is new).
    scope = {"api_key": {"api_key_id": api_key_id}}
    created = post(
        "/v2/budgets",
        {"scope": scope, "limits": {"period": "BUDGET_PERIOD_MONTHLY", "amount": 1}},
    )
    budget = created.get("budget", created)
    budget_ids.append(budget_id(budget))

    print("── Step 3b · API key budget: a cost cap for CI ────────")
    print(f"budget   : {budget_ids[-1]} (created) match={budget.get('match')}")
    print(f"limits   : {budget.get('limits')}")
    time.sleep(BUDGET_PROPAGATION_SECONDS)
    status, _body, headers = call(ci_client, "say ok")  # no identity header: only the key budget applies
    cost_headers = {name: value for name, value in headers.items() if "cost" in name}
    print(f"call     : HTTP {status} through {KEY_NAME}, no identity header")
    print(f"headers  : {cost_headers}")
    print("next     : x-ratelimit-remaining-cost is what the key may still spend this month; on a 200 the other x-ratelimit headers show the platform limit")
    return budget_ids


# ── Step 4 · Who may list budgets ──────────────────────────────────────────────────────────────
# The management key lists budgets. The normal API key from .env is a different credential
# with a different job: it can call models and read traces, and gets a 403 on /v2/budgets.


def step_4_who_may_list() -> None:
    """List budgets with the management key, then try the same with the .env key."""
    budgets = list_budgets()

    print("── Step 4 · Who may list budgets ──────────────────────")
    print(f"mgmt key : {len(budgets)} budgets")
    for budget in budgets:
        scope_kind = next(iter(budget["scope"].keys()))
        rate_limit = budget.get("rateLimit") or budget.get("rate_limit")
        print(f"         : {budget_id(budget)} scope={scope_kind} limits={budget.get('limits')} rate_limit={rate_limit} usage={budget.get('usage')}")
    try:
        orq.budgets.list(limit=5)
        print("api key  : listed budgets (unexpected: the .env key should get a 403)")
    except Exception as error:  # noqa: BLE001  the SDK wraps the 403 in its own error type; the body is the point
        print(f"api key  : {type(error).__name__} {str(error)[:110]}")
    print("next     : ORQ_API_KEY=$ORQ_MANAGEMENT_KEY orq budgets list -o json works; with the .env key the same command is a 403")


# ── Step 5 · Cleanup ───────────────────────────────────────────────────────────────────────────
# Runs in the `finally` below, so it also runs when a step above fails. The management key
# cannot delete itself; that last delete is one CLI command with the login session.


def step_5_cleanup(budget_ids: list[str], api_key_id: str) -> None:
    """Delete the budgets and the API key; try the management key and print the CLI fallback."""
    print("── Step 5 · Cleanup ───────────────────────────────────")
    for one_budget_id in budget_ids:
        print(f"budget   : {one_budget_id} deleted, HTTP {delete('/v2/budgets/' + one_budget_id)}")
    print(f"api key  : {api_key_id} deleted, HTTP {delete('/v2/api-keys/' + api_key_id)}")

    # The token does not embed the key id, so find the management key by its name.
    mine = [
        key
        for key in get("/v2/management-keys", limit=100).get("data", [])
        if key.get("name") == MGMT_KEY_NAME
    ]
    next_step = "unset ORQ_MANAGEMENT_KEY. `make reset` has nothing to do for this module."
    for key in mine:
        mgmt_key_id = key.get("management_key_id") or key.get("id")
        response = httpx.delete(
            f"{settings.base_url}/v2/management-keys/{mgmt_key_id}", headers=MGMT_HEADERS, timeout=30
        )
        if response.status_code < 300:
            print(f"mgmt key : {mgmt_key_id} deleted, HTTP {response.status_code}")
        else:  # a management key cannot delete itself; the CLI session can
            print(f"mgmt key : {mgmt_key_id} not deleted, HTTP {response.status_code} {response.json().get('message')}")
            next_step = f"orq management-keys delete {mgmt_key_id} --force, then {next_step}"
    print(f"next     : {next_step}")


if __name__ == "__main__":
    api_key_id, token = step_1_api_key()
    ci_client = OpenAI(api_key=token, base_url=settings.router_url, timeout=60, max_retries=0)
    budget_ids: list[str] = []
    try:
        step_2_identity(ci_client)
        budget_ids = step_3_budgets(ci_client, api_key_id)
        step_4_who_may_list()
    finally:
        step_5_cleanup(budget_ids, api_key_id)
