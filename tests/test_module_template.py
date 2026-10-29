"""Every module README follows one template, so the lessons read the same."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["Starting point", "Goal", "Why", "The one concept to understand first", "Steps", "Proof", "With your coding agent", "Done when", "Gotchas", "Go further", "End state", "Official docs"]
REQUIRED = {"Starting point", "Goal", "Why", "The one concept to understand first", "Steps", "With your coding agent", "Done when", "Gotchas", "End state", "Official docs"}


def sections(text: str) -> list[str]:
    out, fence = [], False
    for line in text.splitlines():
        fence ^= line.startswith("```")
        if not fence and line.startswith("## "):
            name = line[3:].strip()
            out.append("New in orq.ai" if name.startswith("New in orq.ai") else name)
    return out


def test_every_module_readme_follows_the_template():
    for readme in sorted((ROOT / "modules").glob("*/README.md")):
        found = [s for s in sections(readme.read_text()) if s in ORDER or s == "New in orq.ai"]
        assert REQUIRED <= set(found), (readme, REQUIRED - set(found))
        order = ORDER[:9] + ["New in orq.ai"] + ORDER[9:]
        assert found == sorted(found, key=order.index), (readme, found)


def test_starting_point_names_a_command_and_the_time():
    for readme in sorted((ROOT / "modules").glob("*/README.md")):
        text = readme.read_text()
        start = text.split("## Starting point", 1)[1].split("## Goal", 1)[0]
        assert re.search(r"Command: `(make [a-z-]+( M=[a-z-]+)?)`\. Time: \d+ min", start), readme
        assert "module 0" not in start and "module 1" not in start, readme
