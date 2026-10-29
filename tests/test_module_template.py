"""Every module README follows one template, so the lessons read the same."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["Why", "The one concept to understand first", "Steps", "Proof", "With your coding agent", "Done when", "Gotchas", "Go further", "Official docs"]
REQUIRED = {"Why", "The one concept to understand first", "Steps", "With your coding agent", "Done when", "Gotchas", "Official docs"}


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
        order = ORDER[:7] + ["New in orq.ai"] + ORDER[7:]
        assert found == sorted(found, key=order.index), (readme, found)
