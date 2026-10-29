"""The tracing module's exercises: one change per step, the four tabs, snippets that match the code."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "modules/tracing/run.py"
README = ROOT / "modules/tracing/README.md"
CARD_LABELS = ("**Change**", "**Run**", "**Watch**", "**Why it matters**")


def step_functions():
    tree = ast.parse(RUN.read_text())
    lines = RUN.read_text().splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and re.match(r"step_\d", node.name):
            yield node.name, lines[node.lineno - 1 : node.end_lineno]


def readme_steps():
    text = README.read_text()
    steps = text.split("## Steps", 1)[1].split("\n## ", 1)[0]
    return re.split(r"\n(?=### Step \d)", steps)[1:]


def tab(block: str, name: str) -> str:
    match = re.search(rf'^=== "{name}"\n(.*?)(?=^=== "|\Z)', block, re.S | re.M)
    return match.group(1) if match else ""


def test_one_change_per_step():
    found = list(step_functions())
    assert len(found) == 5
    for name, body in found:
        assert sum(1 for line in body if re.search(r"# CHANGE: .+", line)) == 1, name


def test_unchanged_starter_prints_change_hint():
    for name, body in step_functions():
        assert any("change_hint(" in line for line in body), name


def test_readme_cards_and_tabs():
    steps = readme_steps()
    assert len(steps) == 5
    for block in steps:
        assert '!!! example "Change · Run · Watch"' in block, block[:40]
        for label in CARD_LABELS:
            assert label in block, (block[:40], label)
        assert '=== "Studio"' in block and '=== "Code"' in block, block[:40]


def test_studio_names_match_code_names():
    code = RUN.read_text()
    for block in readme_steps():
        for name in re.findall(r"`(ws-[a-z0-9-]+)", tab(block, "Studio")):
            assert name in code, name


def test_code_tab_snippets_are_in_run_py():
    code_lines = [line.strip() for line in RUN.read_text().splitlines()]
    for block in readme_steps():
        for snippet in re.findall(r"```python\n(.*?)```", tab(block, "Code"), re.S):
            for line in snippet.splitlines():
                line = line.strip()
                if line and "# CHANGE:" not in line:
                    assert line in code_lines, line
