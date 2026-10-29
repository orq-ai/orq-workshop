"""Modules are referred to by name: folders, assets, docs pages and targets carry no number."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_module_folders_and_assets_carry_no_number():
    for d in (ROOT / "modules").iterdir():
        assert not re.match(r"\d", d.name), d
        for a in (d / "assets").glob("*") if (d / "assets").exists() else []:
            assert not re.match(r"\d\d-", a.name), a


def test_docs_wrappers_match_module_slugs():
    slugs = {d.name for d in (ROOT / "modules").iterdir() if d.is_dir()}
    wrappers = {p.stem for p in (ROOT / "docs/modules").glob("*.md")}
    assert slugs <= wrappers, slugs - wrappers


def test_makefile_runs_modules_by_slug():
    out = subprocess.run(["make", "-n", "module", "M=tracing"], cwd=ROOT, capture_output=True, text=True).stdout
    assert "modules/tracing/run.py" in out
    out = subprocess.run(["make", "-n", "m02"], cwd=ROOT, capture_output=True, text=True).stdout
    assert "modules/tracing/run.py" in out  # the old number still works as an alias


OLD_NUMBERS = {"00": "setup", "01": "gateway", "02": "tracing", "03": "smart-routing", "04": "guardrails", "05": "budgets-and-keys", "06": "orqi", "07": "failure-analysis", "08": "managed-agents", "09": "knowledge-base", "10": "mcp-gateway", "11": "simulation", "12": "evals-in-ci", "13": "coding-agents", "14": "alerts-and-webhooks", "15": "advisor-and-sidekick", "16": "red-teaming", "17": "annotation-queues", "18": "trace-insights"}


def test_old_numbered_urls_redirect():
    text = (ROOT / "mkdocs.yml").read_text()  # the file carries !!python tags, so read it as text
    for nn, slug in OLD_NUMBERS.items():
        assert f"modules/{nn}.md: modules/{slug}.md" in text, nn
    for old, new in [("modules/07-concepts.md", "modules/failure-analysis/concepts.md"), ("modules/08-logic.md", "modules/managed-agents/logic.md")] :
        assert f"{old}: {new}" in text, old
