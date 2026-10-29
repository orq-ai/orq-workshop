"""Academy stage pages: symptoms first, orq.ai named early, readable without code.

Pages move to the new template one by one (NEW_TEMPLATE); the rest keep the old concept-page shape until they do.
"""
import re
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
STAGES = ["build", "route", "trace", "find-failures", "evaluate", "gate"]
NEW_TEMPLATE = ["trace"]
OLD_TEMPLATE = [s for s in STAGES if s not in NEW_TEMPLATE]
SECTIONS = ["The problem", "The idea", "What good looks like", "Where teams start", "On orq.ai", "Practice it", "For leaders"]
ACADEMY_HEAD = ["You need this when…", "What's going on"]
ACADEMY_TAIL = ["What it takes", "When you don't need it yet", "What good looks like", "Next"]
TOOL_TOKENS = ("orq.", "make ", "uv run", "`orq", "evaluatorq", "SDK", "CLI")
CODE_TOKENS = ("```", "uv run", "`orq", "orq_ai")
MAKE_TARGET = re.compile(r"\bmake [a-z]+(-[a-z]+)+")  # `make seed-workspace`, not the verb "make"
PLANTED = ["use your judgment", "telling the truth", "read it back", "colleague", "without asking for tracking"]  # the planted behaviors; never named before the simulation


def page(stage: str) -> str:
    return (ROOT / "docs" / "academy" / f"{stage}.md").read_text()


def h2s(text: str) -> list[str]:
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


@pytest.mark.parametrize("stage", OLD_TEMPLATE)
def test_concept_page_sections_and_length(stage):
    text = page(stage)
    assert h2s(text) == SECTIONS, (stage, h2s(text))
    assert 700 <= len(text.split()) <= 1400, (stage, len(text.split()))


@pytest.mark.parametrize("stage", OLD_TEMPLATE)
def test_concept_page_has_no_code_and_no_tool_names_outside_the_orq_sections(stage):
    text = page(stage)
    assert "```" not in text, stage
    before = text.split("## On orq.ai")[0]
    leaders = text.split("## For leaders")[1]
    for tok in TOOL_TOKENS:
        assert tok not in before, (stage, tok)
        assert tok not in leaders, (stage, tok)


@pytest.mark.parametrize("stage", NEW_TEMPLATE)
def test_academy_page_sections(stage):
    heads = h2s(page(stage))
    assert heads[:2] == ACADEMY_HEAD, (stage, heads)
    assert heads[-4:] == ACADEMY_TAIL, (stage, heads)
    middle = heads[2:-4]
    assert "What orq.ai does" in middle and middle.index("What orq.ai does") >= 1, (stage, heads)  # a comparison comes first


@pytest.mark.parametrize("stage", NEW_TEMPLATE)
def test_academy_page_has_widgets(stage):
    text = page(stage)
    assert text.count("data-explainer") == 1, stage
    assert f'class="loop-map" data-current="{stage}"' in text, stage
    assert 'class="storyboard"' in text, stage
    assert 3 <= text.count('class="symptom"') <= 4, stage


@pytest.mark.parametrize("stage", NEW_TEMPLATE)
def test_academy_names_orq_early(stage):
    words = page(stage).split()
    assert any("orq.ai" in w for w in words[: len(words) // 4]), stage


@pytest.mark.parametrize("stage", NEW_TEMPLATE)
def test_academy_page_has_no_code(stage):
    text = page(stage)
    for tok in CODE_TOKENS:
        assert tok not in text, (stage, tok)
    assert not re.search(r"orq\.(?!ai)", text), stage
    assert not MAKE_TARGET.search(text), stage


@pytest.mark.parametrize("stage", STAGES)
def test_storyboards_are_well_formed(stage):
    for block in re.findall(r'<section class="storyboard".*?</section>', page(stage), re.S):
        assert re.search(r'data-status="(awaiting|approved|recorded)"', block), stage
        assert re.search(r"\|\s*#\s*\|\s*Time\s*\|\s*On screen\s*\|\s*Caption\s*\|", block), stage
        rows = [line for line in block.splitlines() if re.match(r"\|\s*\d+\s*\|", line)]
        assert len(rows) >= 3, stage
        assert "Also on screen" in block, stage


def test_academy_pages_do_not_name_the_planted_behaviors():
    text = " ".join(page(s) for s in STAGES).lower() + (ROOT / "docs/academy/index.md").read_text().lower()
    text += (ROOT / "modules/simulation/concepts.md").read_text().lower()
    for term in PLANTED:
        assert term not in text, term
