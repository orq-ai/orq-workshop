"""The site has three layers around one loop: Academy (why), Workshop (how), Onboarding (bringing orq.ai into a company)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STAGES = ["build", "route", "trace", "find-failures", "evaluate", "gate"]
STAGE_LABELS = ["Build", "Route and protect", "Trace", "Find failures", "Evaluate", "Gate and monitor"]


class _Loader(yaml.SafeLoader):
    pass


# mkdocs.yml carries !!python/name tags for markdown extensions; the nav does not need them.
_Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def _config() -> dict:
    return yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=_Loader)


def _nav() -> list:
    return _config()["nav"]


def _tab(name: str) -> list:
    for item in _nav():
        if isinstance(item, dict) and name in item:
            return item[name]
    raise AssertionError(f"no tab {name}")


def _files(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [f for child in node for f in _files(child)]
    if isinstance(node, dict):
        return [f for child in node.values() for f in _files(child)]
    return []


def test_nav_tabs():
    assert [next(iter(item)) for item in _nav()] == ["Home", "Academy", "Workshop", "Onboarding", "Reference"]


def test_academy_has_every_stage():
    files = _files(_tab("Academy"))
    for stage in STAGES:
        assert f"academy/{stage}.md" in files, stage


def test_workshop_groups_modules_by_stage():
    labels = [next(iter(item)) for item in _tab("Workshop") if isinstance(item, dict)]
    assert [label for label in labels if label in STAGE_LABELS] == STAGE_LABELS
    files = _files(_nav())
    for slug in sorted(d.name for d in (ROOT / "modules").iterdir() if d.is_dir()):
        assert files.count(f"modules/{slug}.md") == 1, slug


def test_old_urls_redirect():
    plugins = _config()["plugins"]
    redirects = next(p["redirects"]["redirect_maps"] for p in plugins if isinstance(p, dict) and "redirects" in p)
    old = [f"{s}/index.md" for s in STAGES] + [
        "start/for-leaders.md", "start/academy.md", "start/core-path.md", "start/for-engineers.md",
        "start/already-on-orq.md", "start/index.md", "start/wrap-up.md", "start/orqi.md", "agenda.md",
    ]
    for key in old:
        assert key in redirects, key
    for key, target in redirects.items():
        assert (ROOT / "docs" / target).exists() or target.startswith("http"), (key, target)


def test_every_module_wrapper_names_its_stage():
    for p in (ROOT / "docs/modules").glob("*.md"):
        text = p.read_text()
        assert 'class="stage-chip"' in text, p
        assert re.search(r'Stage: <a href="\.\./\.\./(academy/(build|route|trace|find-failures|evaluate|gate)|workshop)/">', text), p
        assert ("core path" in text) != ("elective" in text), p


CORE_PATH = ["setup", "gateway", "tracing", "managed-agents", "failure-analysis", "evaluators-and-experiments", "simulation", "evals-in-ci"]


def test_audience_pages_link_every_stage_or_module():
    academy = (ROOT / "docs/academy/index.md").read_text()
    assert all(f"{s}.md" in academy for s in STAGES), "academy home must link every stage"
    workshop = (ROOT / "docs/workshop/index.md").read_text()
    for slug in CORE_PATH:
        assert f"../modules/{slug}.md" in workshop, slug
    electives = (ROOT / "docs/workshop/electives.md").read_text()
    all_slugs = {d.name for d in (ROOT / "modules").iterdir() if d.is_dir()}
    for slug in all_slugs - set(CORE_PATH):
        assert f"../modules/{slug}.md" in electives, slug


def test_wrap_up_closes_the_core_path():
    assert "workshop/wrap-up.md" in _files(_nav())
    assert "[Wrap-up](wrap-up.md)" in (ROOT / "docs/workshop/index.md").read_text()
