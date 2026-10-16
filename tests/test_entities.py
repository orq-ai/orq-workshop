"""entities.ensure_external_knowledge_base validates the base URL before it builds the search URL. No network."""

from dataclasses import replace
from types import SimpleNamespace

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


class _Datasets:
    """Fake orq.datasets: one dataset, `rows` datapoints, records what was created."""

    def __init__(self, rows):
        self.rows, self.added, self.searched = rows, [], None

    def list(self, limit, search=None):
        self.searched = search
        return SimpleNamespace(data=[SimpleNamespace(id="d1", display_name="ws-refund-eval")])

    def list_datapoints(self, dataset_id, limit):
        return SimpleNamespace(data=["row"] if self.rows else [])

    def create_datapoint(self, dataset_id, request_body):
        self.added.extend(request_body)


def _ensure(monkeypatch, rows):
    monkeypatch.setattr(entities, "K", lambda name: f"ws-{name}")
    datasets = _Datasets(rows)
    entities.ensure_dataset(orq=SimpleNamespace(datasets=datasets))
    return datasets


def test_dataset_lookup_searches_by_key(monkeypatch):
    assert _ensure(monkeypatch, rows=1).searched == "ws-refund-eval"


def test_dataset_with_rows_is_not_refilled(monkeypatch):
    assert _ensure(monkeypatch, rows=1).added == []


def test_empty_dataset_from_a_failed_seed_is_refilled(monkeypatch):
    assert _ensure(monkeypatch, rows=0).added


class _HostedOrq:
    """Fake orq: no tools or agents exist yet; records what is created."""

    def __init__(self):
        self.agents_created = []
        self.tools = SimpleNamespace(
            list=lambda limit: SimpleNamespace(data=[]), create=lambda request: None
        )

    @property
    def agents(self):
        def retrieve(agent_key):
            raise LookupError(agent_key)

        return SimpleNamespace(retrieve=retrieve, create=lambda **payload: self.agents_created.append(payload))


@pytest.mark.parametrize(
    ("variant", "key", "instructions"),
    [("fixed", "ws-refund-agent-hosted", "fixed"), ("vulnerable", "ws-refund-agent-vulnerable-hosted", "vulnerable")],
)
def test_hosted_agent_has_a_key_per_variant_and_code_tools(monkeypatch, variant, key, instructions):
    monkeypatch.setattr(entities, "K", lambda name: f"ws-{name}")
    orq = _HostedOrq()
    assert entities.ensure_hosted_agent(orq, variant) == key
    (payload,) = orq.agents_created
    assert payload["key"] == key
    assert payload["instructions"].startswith((entities.DATA_DIR / f"{instructions}_instructions.md").read_text())
    assert {tool["type"] for tool in payload["settings"]["tools"]} == {"code"}
