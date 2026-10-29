"""make check M=<module>: the Done when list, verified against orq.ai. Offline, with a fake client."""

import re
from pathlib import Path
from types import SimpleNamespace

from app import checks

ROOT = Path(__file__).resolve().parent.parent
RATING_FIELD = "annotation.01ABC.label"


class Dumpable(dict):
    def model_dump(self, **_):
        return dict(self)


class FakeTraces:
    def __init__(self, traces, spans, rated):
        self._traces, self._spans, self._rated = traces, spans, rated

    def search(self, *, from_, to, limit, filters):
        hits = list(self._traces)
        for f in filters:
            if f["field"] == RATING_FIELD:
                hits = [t for t in hits if t["trace_id"] in self._rated]
            else:
                hits = [t for t in hits if t.get(f["field"]) in f["values"]]
        return Dumpable(data=hits[:limit])

    def list_spans(self, *, trace_id):
        return Dumpable(data=self._spans.get(trace_id, []))

    def list_fields(self):
        return Dumpable(data=[{"name": RATING_FIELD, "label": "Annotation Rating"}])


def fake(rated=True):
    traces = [
        {"trace_id": "t1", "name": "refund-turn", "thread_id": "ws-thread-1"},
        {"trace_id": "t2", "name": "refund-turn", "thread_id": "ws-thread-1"},
        {"trace_id": "t3", "name": "refund_turn", "thread_id": ""},
        {"trace_id": "t4", "name": "refund_langgraph", "thread_id": ""},
    ]
    spans = {"t3": [{"type": "trace", "name": "refund_turn", "parent_span_id": None}] + [{"type": "span.agent_tool_execution", "name": n, "parent_span_id": "r"} for n in ("lookup_order", "get_policy", "issue_refund")]}
    return SimpleNamespace(traces=FakeTraces(traces, spans, {"t3"} if rated else set()))


def test_all_pass_on_complete_state(capsys):
    assert checks.run("tracing", fake()) == 0
    out = capsys.readouterr().out
    assert "✗" not in out and out.count("✓") == 4


def test_missing_annotation_fails_that_check_only(capsys):
    assert checks.run("tracing", fake(rated=False)) == 1
    failed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("✗")]
    assert len(failed) == 1 and "rating" in failed[0]


def test_labels_match_done_when():
    text = (ROOT / "modules/tracing/README.md").read_text().split("## Done when", 1)[1].split("\n## ", 1)[0]
    bullets = [re.sub(r"^- \[ \] ", "", line) for line in text.splitlines() if line.startswith("- [ ] ")]
    assert checks.labels("tracing") == bullets


def test_unknown_module_exits_nonzero_with_list(capsys):
    assert checks.run("nope", fake()) == 1
    assert "tracing" in capsys.readouterr().out


def test_done_when_points_at_make_check():
    text = (ROOT / "modules/tracing/README.md").read_text().split("## Done when", 1)[1].split("\n## ", 1)[0]
    assert "make check M=tracing" in text
