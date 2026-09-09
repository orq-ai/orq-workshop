# 05 · Budgets and keys

!!! abstract "Factor 5: Unify execution state and business state"
    Who is calling, on whose behalf, and how much they may spend are attributes of the request, enforced by the gateway. Not a spreadsheet you reconcile after the invoice.

**Time:** 15 min, instructor demo · **Prereqs:** module 00, workspace admin · **You will have:** a purpose-built API key, an identity for one customer, two budgets that block the third call in a minute, and a clean workspace at the end.

## Why

The refund agent will run in CI and in production under different keys, and it will serve many customers under one key. A budget on the CI key stops a runaway test from burning the month's credits; a budget on a customer identity stops one abusive user from doing the same. Both are one API call, both are enforced before the provider is called, and both give the caller a `429` it can read.

## The one concept to understand first

Two credentials, two jobs. An **API key** calls models. A **Management Key** administers API keys and budgets, and cannot call models. The demo key in `.env` is an all-projects API key; it can list identities and traces, and it gets `403` on `/v2/budgets`. Budgets are scoped to one of six targets (workspace, project, identity, API key, provider, model), carry a period limit in USD or tokens, and optionally a rolling requests-per-minute cap. The most restrictive matching budget wins.

```python
mgmt = Orq(api_key=os.environ["ORQ_MANAGEMENT_KEY"])
mgmt.budgets.create(
    scope={"identity": {"identity_external_id": "customer-user_001"}},
    limits={"period": "BUDGET_PERIOD_MONTHLY", "amount": 5},
    rate_limit={"requests_per_minute": 2},
)
```

## Steps

The run needs a Management Key in the shell. Create it, export it, run, delete it. It never goes into `.env`.

```bash
$ orq management-keys create --help | head -3
Mints a new opaque management key (`sk-orq-<key_id>-<secret>`) in the workspace. The raw secret is returned ONCE in the response and is never retrievable afterwards. ...
$ orq management-keys create --name ws-mgmt-key \
    --permission-mode MANAGEMENT_PERMISSION_MODE_RESTRICTED \
    --access budget=ACCESS_LEVEL_WRITE --access api-key=ACCESS_LEVEL_WRITE --access management-key=ACCESS_LEVEL_WRITE --json
$ export ORQ_MANAGEMENT_KEY=<the "token" from that response>
$ make m05
```

### Step 1 · API keys, and a key for the CI runner

```bash
$ orq api-keys list --json | jq '.[0] | {id, name, permission_mode, project_scope, token}'
{
  "id": "01KTBMFJ2JV9WZN1FSBH60SH8M",
  "name": "API-K",
  "permission_mode": "restricted",
  "project_scope": { "mode": "all" },
  "token": "sk-orq********mYQv1c"
}
$ orq api-keys create --example
{
  "name": "name",
  "permission_mode": "PERMISSION_MODE_UNSPECIFIED"
}
```

A key is either all-projects or single-project (`project_scope`), and either `PERMISSION_MODE_ALL`, `READ_ONLY` or `RESTRICTED` with a per-domain `access` map (`chat_completions`, `dataset`, `eval`, `agent`, ... at `ACCESS_LEVEL_READ` or `WRITE`). A CI runner that runs `make eval` needs to call models and read datasets and evaluators, nothing else. The solution asks for exactly that:

```text
[1] api keys in workspace: 105 (list never returns a token)
[1] created ws-ci-key id=01M21GBK0DT1BXZ8SHR0X8D9FY token=sk-orq-...yjB8 (kept in memory only)
[1] stored  permission_mode=all project_scope={'mode': 'all'} family=workspace_jwt
```

The token is printed once by the API, held in memory for the run, and never logged. Read the `stored` line: on this workspace the API accepted `permission_mode`, `access` and `project_scope` but stored the key as `all`. See the gotchas. The budget in step 3 is what actually limits this key.

### Step 2 · Identities

An identity is the customer the call is made for. Create it once, then tag every call with `X-ORQ-IDENTITY-ID` and traces group under it:

```text
[2] identity exists 01M21F3FT4XNRRAWZGKYRV1H4K external_id=customer-user_001
[2] tagged call 200 trace=cc1c430ed03cfba0a24d48f4b0534dc3  (orq identities list --search customer-user_001)
```

```bash
$ orq identities list --search customer-user_001 --json | jq '.data[] | {_id, external_id}'
{ "_id": "01M21F3FT4XNRRAWZGKYRV1H4K", "external_id": "customer-user_001" }
```

Open Traces, filter by identity `customer-user_001`: the calls from this module and from module 02 sit together.

### Step 3 · Budgets: the third call fails

The identity budget allows 2 requests per minute and USD 5 per month. Three calls, tagged with the identity, through `ws-ci-key`:

```text
[3a] identity budget 01M21GBP4ARB3G5VA343TEQSP9 match={'cel': 'identity == "customer-user_001"'} limits={'period': 'BUDGET_PERIOD_MONTHLY', 'amount': 5} rate_limit={'requestsPerMinute': 2}
[3a] call 1: 200
[3a] call 2: 200
[3a] call 3: 429 {"message": "Rate limit exceeded. Maximum requests allowed per minute.", "type": "rate_limit_error", "param": null, "code": "requests_per_minute_exceeded", "scope_kind": "IDENTITY", "scope_target_id": "customer-user_001", "dimension": "requests"}
     headers: {'x-ratelimit-limit': '2', 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '58s', 'retry-after': '58'}
[3a] usage after: {'amount': 1.23e-05, 'tokens': 37, 'requests': 2}
```

The error body names the budget (`scope_kind`, `scope_target_id`) and the dimension. `code` is what your code should switch on: `requests_per_minute_exceeded`, `cost_budget_exceeded`, `token_budget_exceeded`. The plain `rate_limit_exceeded` is the platform limit, not a budget.

The second budget is a USD 1 monthly cost cap on the CI key. The response headers carry the key's remaining cost capacity:

```text
[3b] api-key budget 01M21GBYEJ66T6VWZ18N2R9SMQ match={'cel': 'api_key == "01M21GBK0DT1BXZ8SHR0X8D9FY"'} limits={'period': 'BUDGET_PERIOD_MONTHLY', 'amount': 1}
[3b] call with ws-ci-key: 200 cost headers={'x-ratelimit-limit-cost': '1', 'x-ratelimit-remaining-cost': '1', 'x-ratelimit-reset-cost': '1908191s'}
```

### Step 4 · Who may list budgets

```text
[4] management key: 2 budgets
     01M21GBYEJ66T6VWZ18N2R9SMQ scope=apiKey limits={'period': 'BUDGET_PERIOD_MONTHLY', 'amount': 1} rate_limit=None usage={'amount': 0, 'tokens': 0, 'requests': 0}
     01M21GBP4ARB3G5VA343TEQSP9 scope=identity limits={'period': 'BUDGET_PERIOD_MONTHLY', 'amount': 5} rate_limit={'requestsPerMinute': 2} usage={'amount': 1.23e-05, 'tokens': 37, 'requests': 2}
[4] normal key: APIDefaultError API error occurred: Status 403. Body: {"code":7,"message":"not authorized for this endpoint"}
```

The CLI reads `ORQ_API_KEY` from the environment when it is set, so the same contrast from the shell:

```bash
$ ORQ_API_KEY=$ORQ_MANAGEMENT_KEY orq budgets list --json
{
  "object": "list"
}
$ ORQ_API_KEY=<the key from .env> orq budgets list --json
Error: error calling operation: HTTP 403:
{"code":7,"message":"not authorized for this endpoint"}
```

(The first list is empty because the run had already cleaned up. Your logged-in `orq` session is a workspace admin and lists budgets too.)

### Step 5 · Cleanup

The run deletes what it made. The management key cannot delete itself, so the last step is one CLI command:

```text
[5] delete budget 01M21GBP4ARB3G5VA343TEQSP9: 200
[5] delete budget 01M21GBYEJ66T6VWZ18N2R9SMQ: 200
[5] delete api key 01M21GBK0DT1BXZ8SHR0X8D9FY: 204
[5] delete management key 01M21G4X19C4C5NWKGTSS7TX8D: 400 managementkeys: a management key cannot modify or delete itself
    run: orq management-keys delete 01M21G4X19C4C5NWKGTSS7TX8D --force
[5] then: unset ORQ_MANAGEMENT_KEY. `make reset` has nothing to do for this module.
```

```bash
$ orq management-keys delete 01M21G4X19C4C5NWKGTSS7TX8D --force --json
{}
$ unset ORQ_MANAGEMENT_KEY
```

If a run dies half way, run it again: it deletes a stale `ws-ci-key` before creating a new one and reuses an existing identity budget. Budgets it did not get to create do not exist.

## With your coding agent

```bash
$ orq launch claude
```

Paste the prompt from `agent_prompt.md` in this module directory:

> Use the orq MCP tool `query_analytics` to break down spend by model for the last 24 hours in this workspace. Give me a table with model, requests and cost, name the most expensive model, and propose one budget for it: scope, period, amount and a requests-per-minute value, with the exact `orq budgets create` command. Do not create it.

## Done when

- [ ] `orq identities list --search customer-user_001` shows the identity, and Traces filtered by it show the tagged calls
- [ ] Your terminal shows a `429` with `code: requests_per_minute_exceeded` and `scope_kind: IDENTITY`
- [ ] `ORQ_API_KEY=$ORQ_MANAGEMENT_KEY orq budgets list --json` works and the `.env` key gets `403`
- [ ] `orq budgets list --json` shows no budget from this run, `orq api-keys list --json | jq '.[] | select(.name=="ws-ci-key")'` is empty, `orq management-keys list` has no `ws-mgmt-key`
- [ ] `ORQ_MANAGEMENT_KEY` is not in `.env` and not in your shell any more

## Gotchas

- Budgets do not apply to legacy keys. The repo's `.env` key is a `workspace_jwt` family key: five calls under a 2 rpm identity budget all returned 200 and usage stayed at 0. The demo therefore makes its calls through the freshly minted `ws-ci-key`.
- Identity for budgets and for trace grouping came from the `X-ORQ-IDENTITY-ID` header. `extra_body={"orq": {"identity": {"id": ...}}}` on `/chat/completions` neither counted against the identity budget nor set `identity_id` on the trace in this run.
- `POST /v2/api-keys` accepted `permission_mode`, `access` and `project_scope` and stored `permission_mode: all`, `project_scope: all`; a write with that key succeeded. The documented `project_scope: {"single": ...}` shape is rejected as an unknown field; `{"mode": "single", "project_id": ...}` is accepted but not stored. Keys minted by `orq setup --local` do show `mode: single`, so treat restricted keys as Studio-or-CLI-login territory until the API catches up, and put the real limit in a budget.
- A management key cannot modify or delete itself. Grant it `management-key` write and it can manage other management keys; deleting its own record is the CLI's job.
- Requests-per-minute is a rolling 60 s window independent of the period. The `x-ratelimit-*` headers show a budget's values only on the `429` it raises; on a `200` they show the platform limit.
- SDK 4.14: `mgmt.budgets.list()` fails on an empty list (`data` missing) and `api_keys.create()` rejects the documented `single` scope. The solution uses `httpx` against `/v2/budgets` and `/v2/api-keys`.

## New in orq 4.11

Budgets became a first-class entity with six scopes, cost, token and requests-per-minute limits, threshold alerts to notifiers, and Management Keys to administer them from code. 4.12 added an activity overview per model and API key.
