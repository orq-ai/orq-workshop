"""Generate the orq.ai-branded splash / OG card (docs/assets/og-image.png).

One hand-designed 1200x630 card, used as the README splash and as the link-unfurl
image referenced by overrides/main.html. Same brand system as the orq.ai site: warm
off-white ground, the signature teal/cyan aurora with a warm orange hint, the
monochrome Orq mark, near-black display type, capability pills, a command line.

The mkdocs `social` plugin can only source faces from Google Fonts, so it cannot use
the self-hosted brand fonts. This renders a static PNG instead; the PNG is committed,
so CI needs nothing extra. Adapted from orq-ai/evaluatorq scripts/gen_og_card.py.

Run:  uv run --with "fonttools[woff]" --with pillow python scripts/gen_og_card.py
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "docs" / "stylesheets" / "fonts"
MARK_WHITE = ROOT / "docs" / "assets" / "orq-mark-white.svg"
OUT = ROOT / "docs" / "assets" / "og-image.png"

W, H = 1200, 630

# orq.ai palette
GROUND = (247, 246, 243)   # warm off-white
INK = (23, 23, 22)         # near-black display
BODY = (92, 90, 86)        # muted body gray
MUTE = (150, 147, 140)     # captions / prompt
TEAL = (114, 239, 227)
CYAN = (150, 214, 226)
ORANGE = (245, 139, 78)    # orq accent
BORDER = (222, 219, 212)

# "orq workshop", with the q of orq in the accent colour.
TITLE_PARTS = [("or", INK), ("q", ORANGE), (" workshop", INK)]
TAGLINE = "Hands-on training for teams building on orq.ai. One refund agent, from the gateway to managed agents."
# The two tracks and what the repo gates itself with: (icon, tile colour, glyph colour, label).
FEATURES = [
    ("target", TEAL, INK, "AI Gateway"),
    ("chat", TEAL, INK, "Managed Agents"),
    ("check", TEAL, INK, "Evals in CI"),
]
INSTALL = "make setup"  # no ampersand: Kurrent Mono has no "&" glyph
LEFT = 96


def load_font(woff2: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a self-hosted .woff2 brand face as a Pillow font (woff2 -> ttf in memory)."""
    f = TTFont(FONTS / woff2)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size)


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def rasterize_svg(path: Path, width: int) -> bytes:
    """SVG to transparent PNG bytes. cairosvg when it has libcairo, else headless Chrome."""
    try:
        import cairosvg

        return cairosvg.svg2png(url=str(path), output_width=width)
    except (ImportError, OSError):
        pass
    chrome = shutil.which("chromium") or shutil.which("google-chrome") or (CHROME if Path(CHROME).exists() else None)
    if not chrome:
        raise SystemExit("need libcairo (pip install cairosvg + brew install cairo) or a Chrome/Chromium binary")
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "mark.html"
        out = Path(tmp) / "mark.png"
        html.write_text(
            "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
            f"img{{display:block;width:{width}px;height:{width}px}}</style></head>"
            f'<body><img src="file://{path}"></body></html>'
        )
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
             "--default-background-color=00000000", f"--screenshot={out}", f"--window-size={width},{width}",
             f"file://{html}"],
            check=True, capture_output=True,
        )
        return out.read_bytes()


def svg_png(path: Path, width: int, recolor: tuple[int, int, int] | None = None) -> Image.Image:
    """Render an SVG to an RGBA image, optionally flat-recolored (keeps original alpha)."""
    img = Image.open(io.BytesIO(rasterize_svg(path, width))).convert("RGBA")
    if recolor is not None:
        solid = Image.new("RGBA", img.size, (*recolor, 0))
        solid.putalpha(img.split()[3])
        img = solid
    return img


def aurora() -> Image.Image:
    """The signature orq.ai glow: teal/cyan upper-centre with a warm orange hint, softly blurred."""
    card = Image.new("RGBA", (W, H), (*GROUND, 255))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([W // 2 - 760, -440, W // 2 + 760, 190], fill=(*TEAL, 66))
    d.ellipse([W // 2 + 120, -360, W // 2 + 940, 150], fill=(*CYAN, 52))
    d.ellipse([W - 520, -320, W + 200, 210], fill=(*ORANGE, 34))  # warm orange hint, top-right
    card.alpha_composite(layer.filter(ImageFilter.GaussianBlur(150)))
    return card


def feature_icon(draw: ImageDraw.ImageDraw, x: int, y: int, kind: str, tile: tuple[int, int, int], glyph: tuple[int, int, int]) -> int:
    """Draw a rounded icon tile with a simple glyph; returns the tile size."""
    s = 48
    draw.rounded_rectangle([x, y, x + s, y + s], radius=13, fill=tile)
    cx, cy = x + s // 2, y + s // 2
    if kind == "check":  # evaluation / CI gate
        draw.line([(x + 13, cy), (x + 21, cy + 8), (x + 35, y + 14)], fill=glyph, width=4, joint="curve")
    elif kind == "target":  # routing / guardrails / the gateway
        draw.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], outline=glyph, width=3)
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=glyph)
    elif kind == "chat":  # the agent talking to a customer
        draw.rounded_rectangle([x + 11, y + 12, x + 37, y + 30], radius=6, outline=glyph, width=3)
        draw.polygon([(x + 17, y + 29), (x + 17, y + 37), (x + 25, y + 29)], fill=glyph)
    return s


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def main() -> None:
    card = aurora()
    draw = ImageDraw.Draw(card)

    # Lockup: monochrome Orq mark + "orq.ai".
    mark = svg_png(MARK_WHITE, 40, recolor=INK)
    card.alpha_composite(mark, (LEFT, 66))
    draw.text((LEFT + 56, 86), "orq.ai", font=load_font("ESKlarheitKurrent-Smbd.woff2", 30), fill=INK, anchor="lm")

    # Title in Kurrent SemiBold.
    title_font = load_font("ESKlarheitKurrent-Smbd.woff2", 108)
    x = LEFT - 6
    for part, colour in TITLE_PARTS:
        draw.text((x, 186), part, font=title_font, fill=colour)
        x += draw.textlength(part, font=title_font)

    # Tagline in Avio Sans.
    tag_font = load_font("AvioSans-Regular.woff2", 34)
    y = 330
    for line in wrap(draw, TAGLINE, tag_font, 940):
        draw.text((LEFT, y), line, font=tag_font, fill=BODY)
        y += 46

    # Icon-led row: the two tracks plus the gate that keeps them honest.
    feat_font = load_font("AvioSans-Medium.woff2", 26)
    x, fy = LEFT, 448
    for kind, tile, glyph, label in FEATURES:
        s = feature_icon(draw, x, fy, kind, tile, glyph)
        lx = x + s + 15
        draw.text((lx, fy + s // 2), label, font=feat_font, fill=INK, anchor="lm")
        x = int(lx + draw.textlength(label, font=feat_font) + 46)

    # Command line in Kurrent Mono, with a muted prompt.
    mono = load_font("ESKlarheitKurrentMono-Md.woff2", 27)
    draw.text((LEFT, H - 72), "$", font=mono, fill=MUTE)
    draw.text((LEFT + 26, H - 72), INSTALL, font=mono, fill=INK)

    card.convert("RGB").save(OUT, "PNG")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
