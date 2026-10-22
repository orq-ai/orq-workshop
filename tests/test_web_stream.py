"""POST /api/chat/stream and the agent graph, with the gateway's HTTP faked. No network."""

import dataclasses
import json

import httpx
from openai import OpenAI
from starlette.testclient import TestClient

from app import web


def _sse(events: list[dict]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _orchestrator_events() -> list[dict]:
    args = json.dumps({"agent_key": "ws-claims-calculator", "input": "x"})
    call = {
        "type": "function_call",
        "id": "fc1",
        "call_id": "c1",
        "name": "call_sub_agent",
        "arguments": args,
    }
    sub = {
        "type": "orq:call_sub_agent",
        "id": "m1",
        "call_id": "c1",
        "name": "call_sub_agent",
        "arguments": "",
        "result": "EUR 400",
    }
    return [
        {"type": "response.created", "response": {"id": "r", "output": []}},
        {"type": "response.output_item.added", "item": {**call, "arguments": ""}},
        {"type": "response.output_item.done", "item": call},
        {"type": "response.output_item.added", "item": {**sub, "arguments": args}},
        {"type": "response.output_item.done", "item": sub},
        {"type": "response.output_text.delta", "delta": "Uitkering "},
        {"type": "response.output_text.delta", "delta": "EUR 400"},
        {
            "type": "response.completed",
            "response": {"id": "r", "output": [], "output_text": "Uitkering EUR 400"},
        },
    ]


def _client(monkeypatch, handler):
    fake = OpenAI(
        api_key="test",
        base_url="https://gateway.test/v3/router",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(web, "make_openai_client", lambda: fake)
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, api_key="test"))


def _events(res) -> list[dict]:
    return [json.loads(line[6:]) for line in res.text.split("\n\n") if line.startswith("data: ")]


def test_stream_reports_each_agent_the_text_and_a_final_turn(monkeypatch):
    sent: list[dict] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=_sse(_orchestrator_events()),
            headers={"content-type": "text/event-stream", "x-orq-trace-id": "trace-9"},
        )

    _client(monkeypatch, gateway)
    res = TestClient(web.app).post(
        "/api/chat/stream",
        json={
            "message": "Ruit kapot",
            "model": "agent/ws-claims-orchestrator",
            "demo": "insurance",
        },
    )

    events = _events(res)
    assert sent[0]["stream"] is True
    nodes = [(e["agent"], e["state"]) for e in events if e["type"] == "node"]
    assert nodes == [
        ("root", "working"),
        ("ws-claims-calculator", "working"),
        ("ws-claims-calculator", "done"),
        ("root", "done"),
    ]
    steps = [(e["id"], e["tool"], e["agent"], e["state"]) for e in events if e["type"] == "step"]
    assert steps == [  # one call id: running from the start, done when the sub-agent finishes
        ("c1", "call_sub_agent", None, "running"),
        ("c1", "call_sub_agent", "ws-claims-calculator", "running"),
        ("c1", "call_sub_agent", "ws-claims-calculator", "done"),
    ]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Uitkering EUR 400"
    done = events[-1]
    assert (
        done["type"] == "done"
        and done["answer"] == "Uitkering EUR 400"
        and done["steps"] == ["ws-claims-calculator"]
    )
    [call] = done["tool_calls"]  # the sub-agent's input and its result travel with the call
    assert (call["agent"], call["input"], call["result"]) == ("ws-claims-calculator", "x", "EUR 400")
    assert [e["result"] for e in events if e["type"] == "step"][-1] == "EUR 400"
    assert done["history"][-1] == {"role": "assistant", "content": "Uitkering EUR 400"}


def test_stream_refuses_plain_models_and_a_guardrail_choice(monkeypatch):
    _client(monkeypatch, lambda request: httpx.Response(500))
    client = TestClient(web.app)
    plain = client.post(
        "/api/chat/stream", json={"message": "hi", "model": "openai/gpt-x", "conversation_id": "s1"}
    )
    guarded = client.post(
        "/api/chat/stream",
        json={"message": "hi", "model": "agent/a", "guardrails": "pii", "conversation_id": "s1"},
    )
    assert plain.status_code == 422 and guarded.status_code == 422
    assert "s1" not in web._busy  # a refused request must not keep the conversation locked


def test_stream_keeps_a_gateway_block_a_plain_reply(monkeypatch):
    body = {"code": "guardrail_error", "failures": [{"id": "g", "stage": "input", "reason": "bsn"}]}
    _client(
        monkeypatch, lambda request: httpx.Response(400, json=body, headers={"x-orq-trace-id": "t"})
    )
    res = TestClient(web.app).post(
        "/api/chat/stream", json={"message": "hi", "model": "agent/a", "conversation_id": "s2"}
    )
    assert res.status_code == 200 and res.json()["blocked"]["failures"][0]["stage"] == "input"
    assert "s2" not in web._busy


def test_full_answer_lists_the_sub_agents_it_called(monkeypatch):
    args = json.dumps({"agent_key": "ws-claims-faq-assistant"})
    call = {"type": "function_call", "call_id": "c1", "name": "call_sub_agent", "arguments": args}
    text = {"type": "output_text", "text": "Klaar.", "annotations": []}
    message = {"type": "message", "role": "assistant", "content": [text]}
    from tests.test_web import _response

    _client(monkeypatch, lambda request: _response([call, message], 3))
    res = TestClient(web.app).post(
        "/api/chat", json={"message": "hi", "model": "agent/ws-claims-orchestrator"}
    )
    assert res.json()["steps"] == ["ws-claims-faq-assistant"]


def test_agent_graph_walks_team_of_agents_and_survives_cycles(monkeypatch):
    teams = {"a": ["b", "c"], "b": ["a"], "c": []}

    class Agents:
        def retrieve(self, agent_key):
            return type(
                "A",
                (),
                {
                    "model_dump": lambda self: {
                        "team_of_agents": [{"key": k} for k in teams[agent_key]]
                    }
                },
            )()

    monkeypatch.setattr(web, "make_orq", lambda: type("O", (), {"agents": Agents()})())
    web._graphs.clear()
    graph = web._agent_graph("a")
    assert [n["id"] for n in graph["nodes"]] == ["a", "b", "c"]
    assert ["a", "b"] in graph["edges"] and ["b", "a"] in graph["edges"]
    assert TestClient(web.app).get("/api/agent-graph?model=openai/gpt-x").json()["nodes"] == []


def test_agent_graph_lists_tools_and_checks_with_evaluator_names(monkeypatch):
    pre = web.settings.prefix
    settings_ = {
        "tools": [{"display_name": "Call Sub-Agent", "action_type": "call_sub_agent"}],
        "evaluators": [{"id": "e1", "execute_on": "output", "sample_rate": 100.0}],
        "guardrails": [{"id": "g1", "execute_on": "input", "sample_rate": 100.0}],
    }

    class Agents:
        def retrieve(self, agent_key):
            return type("A", (), {"model_dump": lambda self: {"settings": settings_}})()

    def ev(i, k):
        return type("E", (), {"id": i, "key": k})()

    evals = type(
        "Ev",
        (),
        {
            "all": lambda self, limit: type(
                "P", (), {"data": [ev("e1", f"{pre}-judge"), ev("g1", f"{pre}-guard")]}
            )()
        },
    )()
    monkeypatch.setattr(
        web, "make_orq", lambda: type("O", (), {"agents": Agents(), "evals": evals})()
    )
    web._graphs.clear()
    web._eval_names.clear()
    [node] = web._agent_graph("solo")["nodes"]
    assert node["tools"] == ["Call Sub-Agent"]
    assert [(c["name"], c["kind"], c["stage"]) for c in node["checks"]] == [
        ("guard", "guardrail", "input"),
        ("judge", "evaluator", "output"),
    ]
    assert "solo" in web._graphs  # one readable agent is enough to cache
