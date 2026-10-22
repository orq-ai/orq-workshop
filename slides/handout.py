"""Printable one-page handout with QR codes: `uvx --with segno python slides/handout.py`, then print slides/handout.html (A4, white)."""

from pathlib import Path

import segno

LINKS = [
    ("Get your API key", "https://workshop.orq.ai", "Your October Insurance workshop API key and onboarding"),
    ("Workshop docs", "https://orq-ai.github.io/orq-workshop", "Every module, step by step"),
    ("Repo", "https://github.com/orq-ai/orq-workshop", "Code, modules, slides"),
    ("orq.ai Studio", "https://my.orq.ai", "Log in with your workshop account"),
    ("orq.ai docs", "https://docs.orq.ai", "Reference for everything in Studio"),
]


def qr(url: str) -> str:
    return segno.make(url, error="m").svg_inline(scale=5, border=1, dark="#000", light="#fff")


cards = "".join(
    f'<div class="card">{qr(u)}<h2>{t}</h2><a>{u.removeprefix("https://")}</a><p>{d}</p></div>' for t, u, d in LINKS
)
HTML = f"""<!doctype html><meta charset="utf-8"><title>orq.ai workshop for October Insurance: quick reference</title>
<style>
@page {{ size: A4; margin: 14mm }}
body {{ font: 11pt/1.4 system-ui, sans-serif; color: #000; background: #fff; margin: 0 auto; width: 182mm }}
@media screen {{ body {{ width: 210mm; min-height: 297mm; box-sizing: border-box; padding: 14mm; border: 1px solid #ccc; margin: 8mm auto }} }}
h1 {{ font-size: 22pt; margin: 0 0 4mm }} h2 {{ font-size: 12pt; margin: 2mm 0 0 }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6mm }}
.card {{ border: 1px solid #000; border-radius: 3mm; padding: 3mm; text-align: center; break-inside: avoid }}
.card svg {{ width: 38mm; height: 38mm }} .card a {{ font: 8pt ui-monospace, monospace; display: block }} .card p {{ margin: 1mm 0 0; font-size: 9pt }}
h3 {{ font-size: 12pt; margin: 6mm 0 2mm; border-bottom: 1px solid #000 }}
pre {{ font: 8.5pt/1.45 ui-monospace, monospace; margin: 0; white-space: pre-wrap }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6mm }}
</style>
<h1>orq.ai workshop for October Insurance: quick reference</h1>
<div class="grid">{cards}</div>
<div class="cols"><div>
<h3>Set up (once)</h3><pre>npm install -g @orq-ai/cli
orq auth login
git clone https://github.com/orq-ai/orq-workshop
cd orq-workshop
orq setup --local --capability gateway
make setup
make doctor && make smoke</pre>
<h3>Main commands</h3><pre>make help       list every target
make seed       create module entities
make traffic    generate traces to analyse
make eval       quality regression gate
make reset      delete what you created
orq doctor      CLI self-check</pre></div><div>
<h3>Slides</h3><pre>make deck D=october-insurance
open http://localhost:8000</pre>
<h3>Stuck?</h3><pre>401 from the router: check .env, it
  beats your shell's ORQ_API_KEY.
Wrong workspace: orq setup --local
  again.
Docs: Troubleshooting in each module.
Raise a hand.</pre></div></div>
"""
Path(__file__).with_name("handout.html").write_text(HTML)
