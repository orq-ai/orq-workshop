"""Version-bound notes live on one dated page; module gotchas stay short."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONED = re.compile(r"SDK 4\.|CLI 1\d|evaluatorq 1\.|API 4\.|\b4\.1[0-9]\b")


def gotchas(text: str) -> str:
    return text.split("## Gotchas", 1)[1].split("\n## ", 1)[0]


def test_module_gotchas_carry_no_version_pins_and_stay_short():
    for readme in (ROOT / "modules").glob("*/README.md"):
        g = gotchas(readme.read_text())
        assert not VERSIONED.search(g), readme
        assert len(re.findall(r"(?m)^- ", g)) <= 6, readme


def test_known_issues_rows_are_dated_and_grouped_by_module():
    text = (ROOT / "docs/reference/known-issues.md").read_text()
    assert re.search(r"^## .+$", text, re.M)
    for line in [l for l in text.splitlines() if l.startswith("- ")]:
        assert re.match(r"- \d{4}-\d{2}-\d{2} ", line), line
