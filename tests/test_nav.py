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
