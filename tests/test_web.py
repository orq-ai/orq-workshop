"""POST /api/chat runs the real loop and tools; only the gateway's HTTP is faked. No network.

The fake answers the two Responses calls of one refund turn: first a `lookup_order` function
call, then the answer. Each response carries an `x-orq-trace-id` header, as the gateway does.
"""

import dataclasses
import json

import httpx
from openai import OpenAI
from starlette.testclient import TestClient

from app import web


def _response(output: list[dict], n: int) -> httpx.Response:
    body = {
        "id": f"resp_{n}",
        "object": "response",
        "created_at": 0,
        "model": "m",
        "output": output,
    }
    return httpx.Response(200, json=body, headers={"x-orq-trace-id": f"trace-{n}"})


def test_chat_returns_answer_tool_calls_and_trace(monkeypatch):
    requests: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            call = {
                "type": "function_call",
                "call_id": "c1",
                "name": "lookup_order",
                "arguments": json.dumps({"order_id": "ord_a1"}),
            }
            return _response([call], 1)
        text = {"type": "output_text", "text": "Refund approved.", "annotations": []}
        return _response([{"type": "message", "role": "assistant", "content": [text]}], 2)

    fake = OpenAI(
        api_key="test",
        base_url="https://gateway.test/v3/router",
        http_client=httpx.Client(transport=httpx.MockTransport(gateway)),
    )
    monkeypatch.setattr(web, "make_openai_client", lambda: fake)
    monkeypatch.setattr(
        web,
        "settings",
        dataclasses.replace(
            web.settings, api_key="test", base_url="https://my.orq.ai", workspace="acme"
        ),
    )

    res = TestClient(web.app).post(
        "/api/chat",
        json={
            "message": "Refund ord_a1, I changed my mind.",
            "conversation_id": "abc",
            "model": "openai/picked",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "Refund approved."
    assert data["tool_calls"] == [{"name": "lookup_order", "ok": True, "error": None}]
    assert data["trace_id"] == "trace-2"  # the last model call of the loop
    assert data["trace_url"] == "https://my.orq.ai/acme/traces/(trace:trace-2)"
    assert data["model"] == "openai/picked"
    # The picker's model reached the gateway on every call of the loop.
    assert all(r["model"] == "openai/picked" for r in requests)
    # The real tool ran: its output went back to the model, and is in the history we return.
    tool_output = json.loads(requests[1]["input"][-1]["output"])
    assert tool_output["ok"] and tool_output["order"]["id"] == "ord_a1"
    assert data["history"][0]["role"] == "system"
    assert data["history"][-1] == {"role": "assistant", "content": "Refund approved."}


def _models_api(monkeypatch, status: int, body) -> None:
    """Fake `GET /v2/models` (and no hosted agent) for /api/models."""
    request = httpx.Request("GET", "https://my.orq.ai/v2/models")
    response = httpx.Response(status, json=body, request=request)
    monkeypatch.setattr(web.httpx, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(web, "_hosted_agent_exists", lambda: False)
    monkeypatch.setattr(web, "_workspace_agents", list)
    monkeypatch.setattr(
        web, "settings", dataclasses.replace(web.settings, model="openai/gpt-5.4-nano")
    )


def test_models_falls_back_when_the_key_cannot_list_them(monkeypatch):
    _models_api(monkeypatch, 403, {"error": "Not authorized for this endpoint"})

    data = TestClient(web.app).get("/api/models").json()

    assert data["default"] == "openai/gpt-5.4-nano"
    assert data["models"][0] == "openai/gpt-5.4-nano"  # the configured MODEL first, once
    assert sorted(data["models"]) == sorted(web.FALLBACK_MODELS)
    assert data["agents"] == []  # not seeded: no hosted agent in the picker


def test_models_lists_only_enabled_chat_models_that_call_tools(monkeypatch):
    def row(model_id, model_type="chat", has_functions=True, enabled=True):
        return {
            "provider": "acme",
            "model_id": model_id,
            "model_type": model_type,
            "has_functions": has_functions,
            "enabled": enabled,
        }

    rows = [
        row("chatty"),
        row("safety-classifier", has_functions=False),
        row("judge", model_type="classify"),
        row("embedder", model_type="embedding"),
        row("switched-off", enabled=False),
    ]
    _models_api(monkeypatch, 200, rows)

    data = TestClient(web.app).get("/api/models").json()

    assert data["models"] == ["openai/gpt-5.4-nano", "acme/chatty"]


def test_hosted_agent_turn_is_one_call_and_orq_runs_the_tools(monkeypatch):
    """`agent/...` sends the text transcript once; tool calls are read from orq's output items."""
    requests: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        call = {
            "type": "function_call",
            "call_id": "c1",
            "name": "ws-lookup_order",
            "arguments": json.dumps({"order_id": "ord_a1"}),
        }
        text = {"type": "output_text", "text": "Refund issued.", "annotations": []}
        message = {"type": "message", "role": "assistant", "content": [text]}
        return _response([call, message], 7)

    fake = OpenAI(
        api_key="test",
        base_url="https://gateway.test/v3/router",
        http_client=httpx.Client(transport=httpx.MockTransport(gateway)),
    )
    monkeypatch.setattr(web, "make_openai_client", lambda: fake)
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, api_key="test"))
    history = [
        {"role": "system", "content": "local prompt"},
        {"role": "user", "content": "Hi"},
        {"type": "function_call", "name": "lookup_order", "arguments": "{}", "call_id": "x"},
        {"role": "assistant", "content": "Hello!"},
    ]

    res = TestClient(web.app).post(
        "/api/chat",
        json={
            "message": "Refund ord_a1",
            "history": history,
            "model": "agent/ws-refund-agent",
        },
    )

    data = res.json()
    assert len(requests) == 1  # orq ran the loop: no tool round trips from our side
    assert requests[0]["model"] == "agent/ws-refund-agent"
    assert requests[0]["input"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Refund ord_a1"},
    ]
    assert data["answer"] == "Refund issued."
    assert data["tool_calls"] == [{"name": "ws-lookup_order", "ok": None, "error": None}]
    assert data["trace_id"] == "trace-7"
    assert data["history"][-2:] == [
        {"role": "user", "content": "Refund ord_a1"},
        {"role": "assistant", "content": "Refund issued."},
    ]


def test_hosted_tool_code_runs_the_same_rules_as_tools_py():
    """The code orq runs is generated from tools.py; executed here it must agree with dispatch()."""
    from app.refund_agent import tools
    from app.refund_agent.entities import hosted_tool_code

    cases = [
        ("lookup_order", {"order_id": "ord_a1"}),
        ("lookup_order", {"order_id": "ord_zz"}),
        (
            "issue_refund",
            {"order_id": "ord_a1", "reason": "changed mind", "post_window_exception": False},
        ),
        (
            "issue_refund",
            {"order_id": "ord_a4", "reason": "broken", "post_window_exception": False},
        ),
        (
            "issue_refund",
            {"order_id": "ord_a6", "reason": "wobbles", "post_window_exception": False},
        ),
        (
            "issue_refund",
            {"order_id": "ord_a3", "reason": "goodwill", "post_window_exception": True},
        ),
        ("get_policy", {"topic": "nope"}),
    ]
    for name, params in cases:
        namespace = {"params": params}
        exec(hosted_tool_code(name), namespace)  # noqa: S102  our own generated code
        assert namespace["result"] == tools.dispatch(tools.OrderStore(), name, params), (
            name,
            params,
        )
    namespace = {"params": {"topic": "refund_basics"}}
    exec(hosted_tool_code("get_policy"), namespace)  # noqa: S102
    assert namespace["result"]["text"] == tools.get_policy("refund_basics")["text"]


def test_backend_shows_session_orders_without_private_fields():
    data = TestClient(web.app).get("/api/backend").json()
    assert data["orders"]
    assert all(set(o) == set(web.ORDER_FIELDS) for o in data["orders"])
    assert {p["topic"] for p in data["policies"]} == set(web.tools.POLICY_TOPICS)


def _guarded_client(monkeypatch, gateway):
    fake = OpenAI(
        api_key="test",
        base_url="https://gateway.test/v3/router",
        http_client=httpx.Client(transport=httpx.MockTransport(gateway)),
    )
    monkeypatch.setattr(web, "make_openai_client", lambda: fake)
    monkeypatch.setattr(
        web, "settings", dataclasses.replace(web.settings, api_key="test", base_url="https://my.orq.ai", workspace="acme")
    )


def test_guardrails_switch_tags_the_request_and_a_block_is_reported(monkeypatch):
    bodies: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        block = {
            "message": "guardrail check failed: orq_pii_detection",
            "type": "guardrail_error",
            "code": "guardrail_error",
            "failures": [{"id": "orq_pii_detection", "stage": "input", "reason": "PII detected: email address"}],
        }
        return httpx.Response(400, json=block, headers={"x-orq-trace-id": "trace-block"})

    _guarded_client(monkeypatch, gateway)
    history = [{"role": "user", "content": "earlier"}]
    res = TestClient(web.app).post(
        "/api/chat", json={"message": "mail me at a@b.co", "history": history, "guardrails": "both"}
    )

    assert res.status_code == 200
    data = res.json()
    assert data["blocked"]["failures"] == [
        {"id": "orq_pii_detection", "stage": "input", "reason": "PII detected: email address"}
    ]
    assert data["trace_url"] == "https://my.orq.ai/acme/traces/(trace:trace-block)"
    assert data["history"] == history  # the blocked turn is not kept
    assert bodies[0]["metadata"] == {"channel": web.CHAT_CHANNELS["both"]}  # what the rule matches on


def test_switch_off_sends_no_tag_and_other_gateway_errors_stay_errors(monkeypatch):
    bodies: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json={"code": "bad_request", "message": "nope"})

    _guarded_client(monkeypatch, gateway)
    res = TestClient(web.app).post("/api/chat", json={"message": "hi"})

    assert res.status_code == 502
    assert "metadata" not in bodies[0]


def test_tool_outcomes_pair_each_call_with_its_result_and_keep_this_turns_only():
    items = [
        {"type": "function_call", "call_id": "old", "name": "lookup_order", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "old", "output": json.dumps({"ok": True})},
        {"type": "function_call", "call_id": "c1", "name": "issue_refund", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": json.dumps({"ok": False, "error": "outside_window"})},
    ]
    assert web._tool_outcomes(items, ["issue_refund"]) == [{"name": "issue_refund", "ok": False, "error": "outside_window"}]
    assert web._tool_outcomes(items, []) == []


def test_tool_outcomes_ignore_history_outputs_that_are_not_json_objects():
    items = [
        {"type": "function_call", "call_id": "old", "name": "lookup_order", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "old", "output": "not json"},
        {"type": "function_call_output", "call_id": "list", "output": "[1]"},
        {"type": "function_call", "call_id": "c1", "name": "issue_refund", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "[1]"},
    ]
    assert web._tool_outcomes(items, ["issue_refund"]) == [{"name": "issue_refund", "ok": None, "error": None}]


def test_a_block_after_a_tool_ran_undoes_the_orders_it_changed(monkeypatch):
    n = 0

    def gateway(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            call = {"type": "function_call", "call_id": "c1", "name": "issue_refund",
                    "arguments": json.dumps({"order_id": "ord_a1", "reason": "changed mind"})}
            return _response([call], 1)
        block = {"message": "blocked", "type": "guardrail_error", "code": "guardrail_error",
                 "failures": [{"id": "orq_pii_detection", "stage": "input", "reason": "PII"}]}
        return httpx.Response(400, json=block, headers={"x-orq-trace-id": "trace-block"})

    _guarded_client(monkeypatch, gateway)
    web._stores.clear()
    res = TestClient(web.app).post(
        "/api/chat", json={"message": "refund ord_a1", "history": [], "conversation_id": "cid", "guardrails": True}
    )

    assert "blocked" in res.json()
    assert web._stores["cid"].orders["ord_a1"]["refunded"] is False  # the refund did not happen


def test_models_without_any_credentials_is_not_a_500(monkeypatch):
    def no_credentials():
        raise SystemExit("no login")

    monkeypatch.setattr(web.settings.__class__, "bearer", lambda self: no_credentials())
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, api_key=""))

    res = TestClient(web.app).get("/api/models")

    assert res.status_code == 200
    assert res.json()["agents"] == []


def test_each_guardrails_choice_sends_its_own_channel_and_unknown_ones_are_refused(monkeypatch):
    bodies: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _response([{"type": "message", "role": "assistant", "status": "completed",
                           "content": [{"type": "output_text", "text": "ok", "annotations": []}]}], len(bodies))

    _guarded_client(monkeypatch, gateway)
    client = TestClient(web.app)
    for choice in ("pii", "refund", "both"):
        assert client.post("/api/chat", json={"message": "hi", "guardrails": choice}).status_code == 200
    assert [b["metadata"]["channel"] for b in bodies] == [web.CHAT_CHANNELS[c] for c in ("pii", "refund", "both")]
    assert len({b["metadata"]["channel"] for b in bodies}) == 3

    assert client.post("/api/chat", json={"message": "hi", "guardrails": "nope"}).status_code == 422
    client.post("/api/chat", json={"message": "hi", "guardrails": ""})
    assert "metadata" not in bodies[-1]


def test_any_failed_turn_undoes_its_refunds_and_frees_the_conversation(monkeypatch):
    n = 0

    def gateway(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            call = {"type": "function_call", "call_id": "c1", "name": "issue_refund",
                    "arguments": json.dumps({"order_id": "ord_a1", "reason": "changed mind"})}
            return _response([call], 1)
        return httpx.Response(500, json={"code": "boom", "message": "upstream"})

    _guarded_client(monkeypatch, gateway)
    web._stores.clear()
    client = TestClient(web.app)
    res = client.post("/api/chat", json={"message": "refund ord_a1", "conversation_id": "cid2"})

    assert res.status_code == 502
    assert web._stores["cid2"].orders["ord_a1"]["refunded"] is False
    assert "cid2" not in web._busy


def test_agents_are_every_live_agent_of_the_workspace_without_versioned_copies(monkeypatch):
    rows = [
        {"key": "zeta", "status": "live"},
        {"key": "zeta_01M5CNKB3ZVEK4BXR12FNFB0T4", "status": "live"},
        {"key": "draft-one", "status": "draft"},
        {"key": f"{web.settings.prefix}-refund-agent", "status": "live"},
        {"key": "Alpha", "status": "live"},
    ]
    request = httpx.Request("GET", "https://my.orq.ai/v2/agents")
    monkeypatch.setattr(web.httpx, "get", lambda *a, **k: httpx.Response(200, json={"data": rows}, request=request))
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, api_key="test"))

    assert web._workspace_agents() == [f"agent/{web.settings.prefix}-refund-agent", "agent/Alpha", "agent/zeta"]


def test_backend_serves_the_insurance_demo_data():
    data = TestClient(web.app).get("/api/backend?demo=insurance").json()

    assert len(data["cases"]) == 15 and data["rules"] and data["prompts"]
    assert [value for value, _ in data["guardrails"]] == ["", *web.insurance.GUARD_CHOICES]


def test_insurance_demo_needs_an_agent_and_uses_its_own_guardrail_channels(monkeypatch):
    bodies: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _response([{"type": "message", "role": "assistant", "status": "completed",
                           "content": [{"type": "output_text", "text": "Gedekt", "annotations": []}]}], len(bodies))

    _guarded_client(monkeypatch, gateway)
    client = TestClient(web.app)

    assert client.post("/api/chat", json={"message": "hi", "demo": "insurance"}).status_code == 422  # a model, not an agent
    ok = client.post("/api/chat", json={"message": "hi", "demo": "insurance", "model": "agent/claims-assessor", "guardrails": "legal"})
    assert ok.status_code == 200
    assert bodies[-1]["metadata"] == {"channel": web.insurance.CHANNELS["legal"]}
    assert client.post("/api/chat", json={"message": "hi", "demo": "insurance", "model": "agent/x", "guardrails": "pii"}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi", "demo": "nope"}).status_code == 422


def test_models_reports_the_claims_agent_the_insurance_demo_starts_on(monkeypatch):
    assert web._insurance_default(["agent/other"]) is None
    assert web._insurance_default(["agent/other", "agent/claims-assessor"]) == "agent/claims-assessor"
    prefixed = f"agent/{web.insurance.agent_keys()[0]}"
    assert web._insurance_default(["agent/claims-assessor", prefixed]) == prefixed
