"""Checks of the loop with a fake router, and of the tools' business rules. No network.

    make toqan-chat-test
"""

from types import SimpleNamespace as NS

import app
from personas import comprador_dispatch, lojista_dispatch


def chunk(content=None, tool=None, model="fake/model", usage=None):
    calls = [NS(index=0, id=tool[0], function=NS(name=tool[1], arguments=tool[2]))] if tool else None
    return NS(model=model, usage=usage, choices=[NS(delta=NS(content=content, tool_calls=calls))])


class FakeRouter:
    def __init__(self, rounds):
        self.rounds, self.sent = list(rounds), []
        self.chat = NS(completions=NS(with_raw_response=NS(create=self.create)))

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return NS(headers={app.TRACE_HEADER: f"t{len(self.sent)}"}, parse=lambda chunks=self.rounds.pop(0): iter(chunks))


def test_turn_joins_streamed_arguments_runs_tool_and_streams_answer():
    router = FakeRouter([
        [chunk(tool=("c1", "calcular_carrinho", '{"skus": ["CAN')), chunk(tool=(None, None, '-01"]}'))],
        [chunk("Total "), chunk("R$ 108,90.", usage=NS(total_tokens=42, model_extra={"server_tool_use": {"advisor_requests": 1}}))],
    ])
    events = list(app.run_turn(router, "toqan@orq/menor-custo", "quanto fica a caneca?", [], "atendimento", stream=True))
    kinds = [e["type"] for e in events]
    assert kinds == ["step", "round", "step", "delta", "delta", "round", "done"], kinds
    assert events[2] == {**events[2], "tool": "calcular_carrinho", "ok": True, "state": "done"}
    assert events[5]["tokens"] == 42 and events[5]["server_tools"] == {"advisor_requests": 1}
    assert events[5]["trace_url"].endswith("(trace:t2)")
    headers = router.sent[0]["extra_headers"]
    assert headers["X-Toqan-Metadata-Usecase"] == "atendimento" and headers["X-Toqan-Metadata-Persona"] == "comprador"
    assert router.sent[0]["reasoning_effort"] == "none"
    assert events[-1]["answer"] == "Total R$ 108,90." and events[-1]["history"][-2]["role"] == "tool"


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
    router = FakeRouter([[chunk("1,99% ao mês.")], [chunk("1,99% ao mês.")]])
    history = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}]
    for h in ([], history):  # with or without a conversation around it, the request is the same
        done = list(app.run_turn(router, "aws/x", "Qual a taxa?", h, "faq", stream=True, persona="lojista"))[-1]
    assert router.sent[0]["messages"] == router.sent[1]["messages"] and "tools" not in router.sent[0]
    assert done["history"][:2] == history and done["history"][-1]["content"] == "1,99% ao mês."


def test_server_tools_skip_smart_routers():
    router = FakeRouter([[chunk("ok")]])
    list(app.run_turn(router, "toqan@orq/menor-custo", "calcule", [], "ferramentas", stream=True))
    sent = router.sent[0]
    assert sent["model"] == app.DEFAULT_MODEL and {"type": "orq:code_interpreter"} in sent["tools"]


def test_public_request_limits(monkeypatch):
    monkeypatch.setattr(app, "workspace_models", lambda: ["aws/x"])
    assert app.request_problem("oi", [], "aws/x") is None
    assert app.request_problem("oi", [], "toqan@orq/menor-custo") is None
    assert app.request_problem("oi", [], "openai/o9-ultra") == "modelo fora da lista da demo"
    assert app.request_problem("x" * 2001, [], "aws/x")
    assert app.request_problem("oi", [{"role": "user", "content": "x"}] * 61, "aws/x")
