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
    assert data["tool_calls"] == ["lookup_order"]
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
            "model": "agent/ws-refund-agent-hosted",
        },
    )

    data = res.json()
    assert len(requests) == 1  # orq ran the loop: no tool round trips from our side
    assert requests[0]["model"] == "agent/ws-refund-agent-hosted"
    assert requests[0]["input"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Refund ord_a1"},
    ]
    assert data["answer"] == "Refund issued."
    assert data["tool_calls"] == ["ws-lookup_order"]
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
