# %% [markdown]
# # 12 · Evals in CI
#
# The two CI gates, green then red, from one script. A gate is an agent run you start from a
# workflow and read as an exit code: `evals/regression.py` scores the refund agent on the dataset and
# exits 1 when a scorer mean drops below its threshold; `evals/redteam_gate.py` replays known
# attacks against `ws-refund-agent` and exits 1 when the resistance rate drops below the bar. The
# same commands run in `.github/workflows/evals.yml`; here you see the exit codes side by side.
#
# | | |
# |---|---|
# | **Time** | 35 min |
# | **Prerequisites** | modules 00 and 07, `make seed` (module 16 explains the attack file in depth, but is not required) |
# | **You will have** | `make eval` green then red, a static red-team gate, three GitHub workflows, and two headless agent runs you executed locally |
#
# This file is both the solution script (`make m12`) and the notebook source (`make notebooks`).
#
#     uv run python modules/12-evals-in-ci/solution/run.py            # all three gates
#     uv run python modules/12-evals-in-ci/solution/run.py --limit 8  # faster, fewer dataset rows
#
# The script exits 0 only when step 1 exits 0, step 2 exits 1 and step 3 exits 0.

# %%
from __future__ import annotations

import argparse
import json
import sys

from app.refund_agent.config import DATA_DIR, ROOT, settings
from evals import redteam_gate, regression

RESULTS = ROOT / "evals" / "results"


def gate(label: str, fn, argv: list[str]) -> int:
    """Run one CI gate in-process and return its exit code. The gate's own tables print between the header and the exit line."""
    header = f"── {label} "
    print(header + "─" * max(3, 55 - len(header)))
    print(f"command  : python -m {fn.__module__} {' '.join(argv)}")
    code = fn(argv)
    print(f"exit     : {code}")
    return code

# %% [markdown]
# `--limit` trims the dataset for a faster run. A notebook kernel starts with its own argv
# (`-f kernel.json`), so there the flags are not parsed and every row runs.

# %%
parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=None, help="dataset rows per regression run (default: all 20)")
args = parser.parse_args([] if "ipykernel" in sys.modules else None)
limit_args = ["--limit", str(args.limit)] if args.limit else []

# %% [markdown]
# ## Step 1 · Quality gate, fixed instructions
#
# The local refund agent with `app/data/fixed_instructions.md`, scored by the three scorers in
# `evals/scorers.py`. Expected exit 0: every mean at or above its threshold.

# %%
fixed = gate("Step 1 · Quality gate, fixed instructions", regression.main, ["--name", settings.key("refund-regression")] + limit_args)
print(f"verdict  : {'green (exit 0, as expected)' if fixed == 0 else 'red: the fixed instructions should pass, read the table above'}")

# %% [markdown]
# ## Step 2 · Quality gate, vulnerable instructions
#
# The same gate on the instructions a careless PR could ship. Expected exit 1. The results go to
# `vulnerable.json` so they do not overwrite step 1's `latest.json`.

# %%
vuln = gate(
    "Step 2 · Quality gate, vulnerable instructions",
    regression.main,
    [
        "--instructions", str(DATA_DIR / "vulnerable_instructions.md"),
        "--out", str(RESULTS / "vulnerable.json"),
        "--name", settings.key("refund-regression"),
    ] + limit_args,
)
print(f"verdict  : {'red (exit 1, as expected)' if vuln == 1 else 'not red: the gate missed the vulnerable instructions'}")

# %% [markdown]
# ## Step 3 · Security gate, static red team
#
# Ten known attacks from `evals/redteam_static.json` against `ws-refund-agent`, judged by the
# OWASP evaluator. Static mode runs no attacker model, which keeps it cheap enough for every PR.
# The gate fails closed: an errored or unevaluated attack exits 1 just like a successful one.

# %%
sec = gate("Step 3 · Security gate, static red team", redteam_gate.main, ["--agent", settings.key("refund-agent")])
print(f"verdict  : {'green (exit 0, as expected)' if sec == 0 else 'red: an attack got through or errored, read the table above'}")

# %% [markdown]
# ## Step 4 · Summary
#
# The three exit codes and the numbers behind them, read back from the JSON files the gates wrote
# (the same files CI uploads as artifacts).

# %%
print("── Step 4 · Summary ───────────────────────────────────")
for label, code, path in [("fixed", fixed, RESULTS / "latest.json"), ("vuln", vuln, RESULTS / "vulnerable.json")]:
    scores = json.loads(path.read_text())["scores"]
    print(f"{label:8} : exit {code}  " + "  ".join(f"{name}={value:.2f}" for name, value in scores.items()))
redteam = json.loads((RESULTS / "redteam.json").read_text())
print(f"redteam  : exit {sec}  resistance={redteam['resistance_rate']:.0%} found={redteam['vulnerabilities_found']}/{redteam['total_attacks']}")
ok = fixed == 0 and vuln == 1 and sec == 0
print(f"verdict  : {'green on fixed, red on vulnerable, red team clean' if ok else 'unexpected exit codes, read the tables above'}")
print("next     : the same commands run on every PR in .github/workflows/evals.yml")
sys.exit(0 if ok else 1)
