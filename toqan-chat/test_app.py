"""Checks of the loop with a fake router, and of the tools' business rules. No network.

    make toqan-chat-test
"""

import copy
from types import SimpleNamespace as NS

import app
from personas import comprador_dispatch, lojista_dispatch


class Item:
    """An output item as the SDK hands it over: attributes, `model_extra` for router-specific fields, `model_dump`."""
    def __init__(self, model_extra=None, **fields):
        self.__dict__.update(fields)
        self.model_extra = model_extra or {}

    def model_dump(self, exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if k != "model_extra" and v is not None}


def completed(*items, usage=None):
    return NS(type="response.completed", response=NS(output=list(items), model="fake/model", usage=usage or NS(total_tokens=1, model_extra={})))


class FakeRouter:
    def __init__(self, rounds):
        self.rounds, self.sent = list(rounds), []
        self.responses = NS(with_raw_response=NS(create=self.create))

    def create(self, **kwargs):
        self.sent.append(copy.deepcopy(kwargs))  # the SDK serializes at call time; the loop keeps growing `input`
        return NS(headers={app.TRACE_HEADER: f"t{len(self.sent)}"}, parse=lambda events=self.rounds.pop(0): iter(events))


def test_turn_runs_our_tool_reports_server_tools_and_streams_answer():
    call = Item(type="function_call", call_id="c1", name="calcular_carrinho", arguments='{"skus": ["CAN-01"]}')
    python = Item(type="orq:code_interpreter", model_extra={"call_id": "s1", "arguments": '{"code": "print(1)"}', "result": {"stdout": "1"}})
    message = Item(type="message", content=[NS(type="output_text", text="Total R$ 108,90.")])
    router = FakeRouter([
        [NS(type="response.output_item.added", item=call), NS(type="response.output_item.done", item=python), completed(call, python)],
        [NS(type="response.output_text.delta", delta="Total "), NS(type="response.output_text.delta", delta="R$ 108,90."),
         completed(message, usage=NS(total_tokens=42, model_extra={"server_tool_use": {"advisor_requests": 1}}))],
    ])
    events = list(app.run_turn(router, "toqan@orq/menor-custo", "quanto fica a caneca?", [], "atendimento", stream=True, conversation="abc123"))
    kinds = [e["type"] for e in events]
    assert kinds == ["step", "server", "round", "step", "delta", "delta", "round", "done"], kinds
    assert events[1]["tool"] == "orq:code_interpreter" and "stdout" in events[1]["result"]
    assert events[3] == {**events[3], "tool": "calcular_carrinho", "ok": True, "state": "done"}
    assert events[6]["tokens"] == 42 and events[6]["server_tools"] == {"advisor_requests": 1} and events[6]["trace_url"].endswith("(trace:t2)")
    sent = router.sent[0]
    assert sent["extra_headers"]["X-Toqan-Metadata-App"] == "toqan-router-demo" and sent["extra_headers"]["X-Toqan-Metadata-Usecase"] == "atendimento"
    assert sent["extra_body"] == {"name": "toqan-router-demo", "thread": {"id": "toqan-router-demo-abc123"}}
    assert sent["store"] is False and sent["tools"][0]["name"] == "buscar_produtos"  # flat Responses function tools
    # round 2 gets every output item back (the orq:* result too) plus our tool's output
    second = router.sent[1]["input"]
    assert [i.get("type") for i in second[1:]] == ["function_call", "orq:code_interpreter", "function_call_output"]
    assert events[-1]["answer"] == "Total R$ 108,90."


def test_mandate_is_enforced_by_the_tool():
    assert comprador_dispatch("pagar", {"skus": ["BAR-01"], "metodo": "pix"})["error"] == "acima_do_mandato_confirme_com_o_cliente"
    assert comprador_dispatch("pagar", {"skus": ["KIT-99", "BAR-01"], "metodo": "cartao", "parcelas": 12})["ok"] is False
    pix = comprador_dispatch("pagar", {"skus": ["CAN-01"], "metodo": "pix"})
    assert pix["ok"] and pix["valor"] == round((89.0 + 19.90) * 0.95, 2)  # frete below R$ 199, 5% off on Pix
    sete = comprador_dispatch("pagar", {"skus": ["CAF-01"], "metodo": "cartao", "parcelas": 7})
    assert sete["valor_total"] > 189.0  # interest above 6x; free shipping from R$ 199 does not apply to 189
    assert comprador_dispatch("buscar_produtos", {"termo": "café", "preco_max": 200})["produtos"][0]["sku"] == "CAF-01"


def test_merchant_tools():
    assert lojista_dispatch("consultar_transacao", {"id": "t-503"})["status"] == "recusada"
    assert lojista_dispatch("gerar_link_pagamento", {"valor": 6000, "descricao": "x"})["ok"] is False
    assert lojista_dispatch("gerar_link_pagamento", {"valor": 350, "descricao": "bolo"})["link"].startswith("https://")
    assert lojista_dispatch("resumo_vendas", {"periodo": "7d"})["vendas"] == 141


def test_faq_is_one_cacheable_call():
    answer = lambda: [completed(Item(type="message", content=[NS(type="output_text", text="1,99% ao mês.")]))]
    router = FakeRouter([answer(), answer()])
    history = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}]
    for h in ([], history):  # with or without a conversation around it, the request is the same
        done = list(app.run_turn(router, "aws/x", "Qual a taxa?", h, "faq", stream=True, persona="lojista"))[-1]
    assert router.sent[0]["input"] == router.sent[1]["input"] and "tools" not in router.sent[0]
    assert done["history"][:2] == history and done["answer"] == "1,99% ao mês."


def test_server_tools_skip_smart_routers():
    router = FakeRouter([[completed()]])
    list(app.run_turn(router, "toqan@orq/menor-custo", "calcule", [], "ferramentas", stream=True))
    sent = router.sent[0]
    assert sent["model"] == app.DEFAULT_MODEL and {"type": "orq:code_interpreter"} in sent["tools"]


def test_public_request_limits(monkeypatch):
    monkeypatch.setattr(app, "workspace_models", lambda: ["aws/x"])
    assert app.request_problem("oi", [], "aws/x") is None
    assert app.request_problem("oi", [], "toqan@orq/menor-custo") is None
    assert app.request_problem("oi", [], "openai/o9-ultra") == "modelo fora da lista da demo"
    assert app.request_problem("x" * 2001, [], "aws/x")
    assert app.request_problem("oi", [{"role": "user", "content": "x"}] * 151, "aws/x")
