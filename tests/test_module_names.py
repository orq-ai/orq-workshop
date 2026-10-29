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
