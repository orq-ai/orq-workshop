"""Module 12 solution: the two CI gates, green then red, from one script.

    uv run python modules/12-evals-in-ci/solution/run.py            # all three gates
    uv run python modules/12-evals-in-ci/solution/run.py --limit 8  # faster, fewer dataset rows

Step 1 runs evals/regression.py on the fixed instructions (expected exit 0), step 2 on the
vulnerable ones (expected exit 1), step 3 runs evals/redteam_gate.py against ws-refund-agent.
The same commands run in .github/workflows/evals.yml; here you see the exit codes side by side.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.refund_agent.config import DATA_DIR, ROOT, settings
from evals import redteam_gate, regression

RESULTS = ROOT / "evals" / "results"


def gate(label: str, fn, argv: list[str]) -> int:
    print(f"\n===== {label}: python -m {fn.__module__} {' '.join(argv)}")
    code = fn(argv)
    print(f"===== {label}: exit {code}")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="dataset rows per regression run (default: all 20)")
    args = ap.parse_args(argv)
    lim = ["--limit", str(args.limit)] if args.limit else []

    fixed = gate("1 quality, fixed instructions", regression.main, ["--name", settings.key("refund-regression")] + lim)
    vuln = gate("2 quality, vulnerable instructions", regression.main,
                ["--instructions", str(DATA_DIR / "vulnerable_instructions.md"), "--out", str(RESULTS / "vulnerable.json"),
                 "--name", settings.key("refund-regression")] + lim)
    sec = gate("3 security, static red team", redteam_gate.main, ["--agent", settings.key("refund-agent"), "--max-static-datapoints", "8"])

    print("\n===== summary")
    for label, code, path in [("fixed", fixed, RESULTS / "latest.json"), ("vulnerable", vuln, RESULTS / "vulnerable.json")]:
        scores = json.loads(path.read_text())["scores"]
        print(f"  quality  {label:10} exit {code}  " + "  ".join(f"{k}={v:.2f}" for k, v in scores.items()))
    rt = json.loads((RESULTS / "redteam.json").read_text())
    print(f"  security fixed      exit {sec}  resistance={rt['resistance_rate']:.0%} found={rt['vulnerabilities_found']}/{rt['total_attacks']}")
    ok = fixed == 0 and vuln == 1 and sec == 0
    print("OK: green on fixed, red on vulnerable, red team clean" if ok else "unexpected exit codes, read the tables above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
