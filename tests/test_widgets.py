"""Academy widgets follow one markup contract, and the page reads without JavaScript."""

import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STAGES = ["build", "route", "trace", "find-failures", "evaluate", "gate"]
MODES = {"build": "development", "route": "production", "trace": "production", "find-failures": "development", "evaluate": "development", "gate": "production"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children, self.text = tag, dict(attrs), parent, [], ""

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def all_text(self):
        return self.text + "".join(c.all_text() for c in self.children)


class Tree(HTMLParser):
    VOID = {"br", "img", "input", "hr", "meta", "link", "source", "wbr"}

    def __init__(self):
        super().__init__()
        self.root = Node("root", [], None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in self.VOID:
            self.cur = node

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.text += data


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    subprocess.run(["uv", "run", "mkdocs", "build", "--strict", "-q", "-d", str(out)], cwd=ROOT, check=True)
    built = {}
    for html in sorted((out / "academy").rglob("index.html")):
        tree = Tree()
        tree.feed(html.read_text())
        built[str(html.relative_to(out))] = tree.root
    return built


def find(root, pred):
    return [n for n in root.walk() if pred(n)]


def ids_in(node):
    return {n.attrs["id"] for n in node.walk() if "id" in n.attrs}


def test_explainer_targets_exist(pages):
    for name, root in pages.items():
        for ex in find(root, lambda n: "data-explainer" in n.attrs):
            ids = ids_in(ex)
            for step in find(ex, lambda n: n.tag == "li" and any(k in n.attrs for k in ("data-show", "data-hot", "data-bad"))):
                for key in ("data-show", "data-hot", "data-bad"):
                    for target in (step.attrs.get(key) or "").split():
                        assert target in ids, (name, key, target)


def test_explainer_content_is_in_the_markup(pages):
    for name, root in pages.items():
        for ex in find(root, lambda n: "data-explainer" in n.attrs):
            steps = [n for n in find(ex, lambda n: n.tag == "li" and "data-show" in n.attrs)]
            assert steps, name
            assert all(s.all_text().strip() for s in steps), name
            for node in ex.walk():
                assert "hidden" not in node.attrs, (name, node.attrs.get("id"))
                assert "display:none" not in (node.attrs.get("style") or "").replace(" ", ""), (name, node.attrs.get("id"))


def test_chooser_targets_exist(pages):
    for name, root in pages.items():
        for chooser in find(root, lambda n: "data-chooser" in n.attrs):
            ids = ids_in(chooser)
            options = find(chooser, lambda n: "data-lights" in n.attrs)
            assert options, name
            for opt in options:
                assert (opt.attrs.get("data-why") or "").strip(), name
                for target in opt.attrs["data-lights"].split():
                    assert target in ids, (name, target)


def test_loop_map_is_complete(pages):
    for name, root in pages.items():
        for loop in find(root, lambda n: "loop-map" in n.classes()):
            stages = find(loop, lambda n: "loop-stage" in n.classes())
            assert [s.attrs.get("data-stage") for s in stages] == STAGES, name
            assert all(s.attrs.get("data-mode") == MODES[s.attrs["data-stage"]] for s in stages), name
            if "data-current" in loop.attrs:
                assert loop.attrs["data-current"] in STAGES, name


def test_widgets_bind_on_document_subscription():
    js = (ROOT / "docs/js/academy.js").read_text()
    assert "document$.subscribe" in js
    assert "DOMContentLoaded" not in js
