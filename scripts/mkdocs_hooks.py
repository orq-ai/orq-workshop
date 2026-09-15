"""MkDocs hook. Module READMEs live outside docs/ and are pulled in by snippets, so a
`![...](assets/x.png)` in modules/NN-name/README.md resolves on GitHub but not on the
site. Register every modules/*/assets/*.png as docs-relative `modules/assets/<name>`,
which is exactly where the snippet-included page looks for it."""

from pathlib import Path

import termynal.markdown
from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]

# termynal's preprocessor runs at priority 35, before pymdownx.snippets (32), so a
# `<!-- termynal -->` fence inside a snippet-included README is never seen. Run it after.
termynal.markdown.TERMYNAL_PREPROCESSOR_PRIORITY = 30


def on_files(files, config):
    for png in sorted(ROOT.glob("modules/*/assets/*.png")):
        files.append(File.generated(config, f"modules/assets/{png.name}", abs_src_path=str(png)))
    return files
