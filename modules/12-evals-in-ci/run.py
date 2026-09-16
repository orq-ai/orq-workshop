"""Module 12 starter: run the CI gates locally, green then red.

A gate is an agent run you read as an exit code. `evals/regression.py` exits 1 when a scorer mean
drops below its threshold; `evals/redteam_gate.py` exits 1 when the refund agent resists fewer
known attacks than the bar. CI runs the same two commands on every pull request.

    uv run python modules/12-evals-in-ci/run.py
    uv run python modules/12-evals-in-ci/run.py --limit 8   # fewer dataset rows

Step 1 works as is. Fill in steps 2 and 3 (see the TODO lines); an unfilled step says so in its
output block. The solution is in solution/run.py.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.refund_agent.config import DATA_DIR, ROOT, settings  # noqa: F401  (DATA_DIR: step 2)
from evals import redteam_gate, regression  # noqa: F401  (redteam_gate: step 3)

RESULTS = ROOT / "evals" / "results"


def gate(label: str, fn, argv: list[str]) -> int:
    """Run one CI gate in-process and return its exit code. The gate's own tables print between the header and the exit line."""
    header = f"── {label} "
    print(header + "─" * max(3, 55 - len(header)))
    print(f"command  : python -m {fn.__module__} {' '.join(argv)}")
    code = fn(argv)
    print(f"exit     : {code}")
    return code


def main(argv: list[str] | None = None) -> int:
    """Run the gates in order and print a summary. Exits 0 when the fixed instructions pass."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit_args = ["--limit", str(args.limit)] if args.limit else []

    # ── Step 1 · Quality gate, fixed instructions ──
    # The local agent with the fixed instructions. Expected exit 0.
    fixed = gate("Step 1 · Quality gate, fixed instructions", regression.main, ["--name", settings.key("refund-regression")] + limit_args)

    # ── Step 2 · Quality gate, vulnerable instructions ──
    # The same gate on the instructions a careless PR could ship. Expected exit 1.
    # TODO step 2: run regression.main again with --instructions app/data/vulnerable_instructions.md
    #              and --out evals/results/vulnerable.json. Expect exit 1.
    vuln = 1
    print("── Step 2 · Quality gate, vulnerable instructions ─────")
    print("TODO     : fill in the regression.main call on the vulnerable instructions, then rerun")

    # ── Step 3 · Security gate, static red team ──
    # Ten known attacks against ws-refund-agent. Expected exit 0; an errored attack also exits 1.
    # TODO step 3: run redteam_gate.main(["--agent", settings.key("refund-agent")]). Expect exit 0.
    sec = 0
    print("── Step 3 · Security gate, static red team ────────────")
    print("TODO     : fill in the redteam_gate.main call, then rerun")

    # ── Step 4 · Summary ──
    print("── Step 4 · Summary ───────────────────────────────────")
    scores = json.loads((RESULTS / "latest.json").read_text())["scores"]
    print(f"fixed    : exit {fixed}  " + "  ".join(f"{name}={value:.2f}" for name, value in scores.items()))
    print(f"vulnerab : exit {vuln}  (TODO: step 2 not run)")
    print(f"redteam  : exit {sec}  (TODO: step 3 not run)")
    return 0 if fixed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
