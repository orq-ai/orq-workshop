"""Export diagram sources (HTML with inline SVG) to PNG, diagram only, 2x (`make diagrams`).

    uv run --with playwright python scripts/export_diagrams.py [file.html ...]

No arguments exports every modules/*/assets/*.html and docs/assets/diagrams/*.html; the PNG
lands next to its source with the same stem. The PNGs are committed: GitHub renders the
README from them, and scripts/mkdocs_hooks.py registers them for the docs site.
Needs a Playwright Chromium once: `uv run --with playwright playwright install chromium`.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
files = [Path(a) for a in sys.argv[1:]] or sorted(
    [*ROOT.glob("modules/*/assets/*.html"), *ROOT.glob("docs/assets/diagrams/*.html")]
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    # 2x device scale: the docs site shows the PNG at half its pixel size, so text stays crisp
    # on retina screens.
    page = browser.new_page(device_scale_factor=2)
    for src in files:
        page.goto(src.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        # The brand web fonts load after the page is "loaded"; screenshot before they arrive
        # and the labels render in the fallback face.
        page.evaluate("document.fonts.ready")
        out = src.with_suffix(".png")
        # Screenshot the <svg> element only (no page margins) with a transparent background,
        # so the PNG takes the background of whichever page shows it (GitHub or the docs site).
        page.locator("svg").first.screenshot(path=str(out), omit_background=True)
        print(f"{out}  {out.stat().st_size // 1024} KB")
    browser.close()
