"""Module 12 starter: run the CI gates locally, green then red.

    uv run python modules/12-evals-in-ci/run.py
    uv run python modules/12-evals-in-ci/run.py --limit 8   # fewer dataset rows

Step 1 works as is. Fill in steps 2 and 3 (see the TODO lines). The solution is in solution/run.py.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.refund_agent.config import DATA_DIR, ROOT, settings  # noqa: F401  (DATA_DIR: step 2)
from evals import redteam_gate, regression  # noqa: F401  (redteam_gate: step 3)

RESULTS = ROOT / "evals" / "results"


def gate(label: str, fn, argv: list[str]) -> int:
    print(f"\n===== {label}: python -m {fn.__module__} {' '.join(argv)}")
    code = fn(argv)
    print(f"===== {label}: exit {code}")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    lim = ["--limit", str(args.limit)] if args.limit else []

    fixed = gate("1 quality, fixed instructions", regression.main, ["--name", settings.key("refund-regression")] + lim)
    # TODO step 2: run regression.main again with --instructions app/data/vulnerable_instructions.md
    #              and --out evals/results/vulnerable.json. Expect exit 1.
    vuln = 1
    # TODO step 3: run redteam_gate.main(["--agent", settings.key("refund-agent"), "--max-static-datapoints", "8"]). Expect exit 0.
    sec = 0

    print("\n===== summary")
    scores = json.loads((RESULTS / "latest.json").read_text())["scores"]
    print(f"  quality  fixed      exit {fixed}  " + "  ".join(f"{k}={v:.2f}" for k, v in scores.items()))
    print(f"  quality  vulnerable exit {vuln}  (TODO)")
    print(f"  security fixed      exit {sec}  (TODO)")
    return 0 if fixed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
