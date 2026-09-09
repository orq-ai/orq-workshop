"""MkDocs hook. Module READMEs live outside docs/ and are pulled in by snippets, so a
`![...](assets/x.png)` in modules/NN-name/README.md resolves on GitHub but not on the
site. Register every modules/*/assets/*.png as docs-relative `modules/assets/<name>`,
which is exactly where the snippet-included page looks for it."""

from pathlib import Path

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]


def on_files(files, config):
    for png in sorted(ROOT.glob("modules/*/assets/*.png")):
        files.append(File.generated(config, f"modules/assets/{png.name}", abs_src_path=str(png)))
    return files
