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
        "/api/chat", json={"message": "Refund ord_a1, I changed my mind.", "conversation_id": "abc"}
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "Refund approved."
    assert data["tool_calls"] == ["lookup_order"]
    assert data["trace_id"] == "trace-2"  # the last model call of the loop
    assert data["trace_url"] == "https://my.orq.ai/acme/traces?query=trace_id%3Ais%3Atrace-2"
    # The real tool ran: its output went back to the model, and is in the history we return.
    tool_output = json.loads(requests[1]["input"][-1]["output"])
    assert tool_output["ok"] and tool_output["order"]["id"] == "ord_a1"
    assert data["history"][0]["role"] == "system"
    assert data["history"][-1] == {"role": "assistant", "content": "Refund approved."}
