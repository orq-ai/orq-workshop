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
