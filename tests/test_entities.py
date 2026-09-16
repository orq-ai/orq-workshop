"""entities.ensure_external_knowledge_base validates the base URL before it builds the search URL. No network."""

from dataclasses import replace

import pytest

from app.refund_agent import entities


class _Boom(Exception):
    pass


class _Orq:
    class knowledge:
        @staticmethod
        def list(limit):
            raise _Boom


def test_missing_edge_url_fails_before_any_api_call(monkeypatch):
    monkeypatch.setattr(entities, "settings", replace(entities.settings, edge_url=""))
    with pytest.raises(RuntimeError, match="WS_EDGE_URL"):
        entities.ensure_external_knowledge_base(orq=object(), api_url="")


def test_base_url_is_accepted_and_reaches_the_api(monkeypatch):
    monkeypatch.setattr(entities, "settings", replace(entities.settings, edge_url=""))
    with pytest.raises(_Boom):
        entities.ensure_external_knowledge_base(orq=_Orq(), api_url="https://edge.example/")
