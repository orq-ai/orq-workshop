"""Stage concept pages: the idea first, orq.ai last, readable without code."""
import re
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
STAGES = ["build", "route", "trace", "find-failures", "evaluate", "gate"]
SECTIONS = ["The problem", "The idea", "What good looks like", "Where teams start", "On orq.ai", "Practice it", "For leaders"]
TOOL_TOKENS = ("orq.", "make ", "uv run", "`orq", "evaluatorq", "SDK", "CLI")
PLANTED = ["use your judgment", "telling the truth", "read it back", "colleague", "without asking for tracking"]  # the planted behaviors; never named before the simulation

@pytest.mark.parametrize("stage", STAGES)
def test_concept_page_sections_and_length(stage):
    text = (ROOT / "docs" / stage / "index.md").read_text()
    heads = [l[3:].strip() for l in text.splitlines() if l.startswith("## ")]
    assert heads == SECTIONS, (stage, heads)
    assert 700 <= len(text.split()) <= 1400, (stage, len(text.split()))

@pytest.mark.parametrize("stage", STAGES)
def test_concept_page_has_no_code_and_no_tool_names_outside_the_orq_sections(stage):
    text = (ROOT / "docs" / stage / "index.md").read_text()
    assert "```" not in text, stage
    before = text.split("## On orq.ai")[0]
    leaders = text.split("## For leaders")[1]
    for tok in TOOL_TOKENS:
        assert tok not in before, (stage, tok)
        assert tok not in leaders, (stage, tok)

def test_evaluate_stage_does_not_name_the_planted_behaviors():
    text = ((ROOT / "docs/evaluate/index.md").read_text() + (ROOT / "modules/simulation/concepts.md").read_text()).lower()
    for term in PLANTED:
        assert term not in text, term
