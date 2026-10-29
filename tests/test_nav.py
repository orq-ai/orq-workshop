"""The site is organized around the loop: one tab per stage, a concept page on top of each."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGES = ["build", "route", "trace", "find-failures", "evaluate", "gate"]


def test_nav_is_the_loop():
    text = (ROOT / "mkdocs.yml").read_text().split("\nnav:\n", 1)[1]
    tabs = re.findall(r"^  - ([^:\n]+):", text, re.M)
    assert tabs == ["Home", "Start here", "Build", "Route and protect", "Trace", "Find failures", "Evaluate", "Gate and monitor", "Reference"]
    for stage in STAGES:
        assert f"{stage}/index.md" in text, stage


def test_every_module_wrapper_names_its_stage():
    for p in (ROOT / "docs/modules").glob("*.md"):
        text = p.read_text()
        assert 'class="stage-chip"' in text, p
        assert re.search(r'Stage: <a href="\.\./\.\./(build|route|trace|find-failures|evaluate|gate|start)/">', text), p
        assert ("core path" in text) != ("elective" in text), p


CORE_PATH = ["setup", "gateway", "tracing", "managed-agents", "failure-analysis", "evaluators-and-experiments", "simulation", "evals-in-ci"]


def test_audience_pages_link_every_stage_or_module():
    leaders = (ROOT / "docs/start/for-leaders.md").read_text()
    assert all(f"../{s}/index.md" in leaders for s in STAGES), "leaders page must link every stage"
    engineers = (ROOT / "docs/start/for-engineers.md").read_text()
    for slug in CORE_PATH:
        assert f"../modules/{slug}.md" in engineers, slug
    already = (ROOT / "docs/start/already-on-orq.md").read_text()
    all_slugs = {d.name for d in (ROOT / "modules").iterdir() if d.is_dir()}
    for slug in all_slugs - set(CORE_PATH):
        assert f"../modules/{slug}.md" in already, slug


def test_wrap_up_closes_the_core_path():
    assert "start/wrap-up.md" in (ROOT / "mkdocs.yml").read_text()
    core = (ROOT / "docs/start/core-path.md").read_text()
    assert "[Wrap-up](wrap-up.md)" in core
