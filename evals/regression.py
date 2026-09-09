"""Quality regression gate: `uv run python -m evals.regression` (also `make eval`).

Runs the local refund agent over app/data/dataset.jsonl with evaluatorq, scores every
row with the scorers in evals/scorers.py and exits 1 when a mean drops below its
threshold. This is a regression gate, not a benchmark: the thresholds say "no worse
than the agent we shipped", and they only move when someone edits this file on purpose.

    python -m evals.regression                                              # fixed instructions
    python -m evals.regression --instructions app/data/vulnerable_instructions.md
    python -m evals.regression --limit 5                                    # quick local check

Results sync to the Studio as an Experiment run when ORQ_API_KEY is set (it is, from .env).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from evaluatorq import DataPoint, evaluatorq, job

from app.refund_agent.agent import chat
from app.refund_agent.config import DATA_DIR, ROOT  # loads .env; evaluatorq reads ORQ_API_KEY at call time
from app.refund_agent.tools import OrderStore
from evals.scorers import EVALUATORS

# Calibrated on 2026-09-08 over the 20-row dataset at temperature 0: fixed instructions scored
# 0.85 / 1.00 / 0.70 and 0.90 / 1.00 / 0.75 in two runs, vulnerable ones 0.75 / 1.00 / 0.55.
# 2026-09-09, after judge_prompt.md gained the "change of mind is valid in-window" line: 0.85 /
# 1.00 / 0.75. The judge bar is 0.70, not 0.75: an LLM judge lands on the threshold often enough
# that a zero-margin gate would flake on green code.
THRESHOLDS = {"decision_matches": 0.80, "no_pii_leak": 1.00, "policy_judge": 0.70}
RESULTS = ROOT / "evals" / "results" / "latest.json"


def load_rows(limit: int | None = None) -> list[DataPoint]:
    rows = [json.loads(l) for l in (DATA_DIR / "dataset.jsonl").read_text().splitlines() if l.strip()]
    return [DataPoint(inputs=r["inputs"], expected_output=r["expected_output"]) for r in rows[:limit]]


def rows_detail(results) -> list[dict]:
    """One record per dataset row: input, output and every scorer verdict with its explanation."""
    out = []
    for dp in results:
        for jr in dp.job_results or []:
            output = jr.output if isinstance(jr.output, dict) else {"answer": str(jr.output)}
            scores = {}
            for s in jr.evaluator_scores or []:
                ok = False
                if not s.error and s.score is not None:
                    ok = s.score.pass_ if s.score.pass_ is not None else bool(s.score.value)
                scores[s.evaluator_name] = {"pass": bool(ok), "explanation": (s.error or getattr(s.score, "explanation", None) or "")[:300]}
            out.append({"message": dp.data_point.inputs.get("message"), "expected_decision": dp.data_point.inputs.get("expected_decision"),
                        "tool_calls": output.get("tool_calls", []), "answer": output.get("answer", ""), "trace_id": output.get("trace_id"),
                        "error": str(dp.error or jr.error or "") or None, "scores": scores})
    return out


def means(rows: list[dict]) -> dict[str, float]:
    """Mean pass rate per scorer. Errors and missing scores count as 0."""
    per: dict[str, list[float]] = {}
    for r in rows:
        for name, s in r["scores"].items():
            per.setdefault(name, []).append(1.0 if s["pass"] else 0.0)
    return {k: round(sum(v) / len(v), 3) for k, v in per.items() if v}


def summary_md(name: str, instructions: str, scores: dict[str, float], url: str, rows: int) -> str:
    lines = [f"## Eval gate: {name}", "", f"Instructions: `{instructions}` · rows: {rows}", "",
             "| scorer | mean | threshold | status |", "|---|---|---|---|"]
    for k, thr in THRESHOLDS.items():
        m = scores.get(k, 0.0)
        lines.append(f"| {k} | {m:.2f} | {thr:.2f} | {'PASS' if m >= thr else 'FAIL'} |")
    if url:
        lines += ["", f"Experiment: {url}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instructions", default=str(DATA_DIR / "fixed_instructions.md"))
    ap.add_argument("--limit", type=int, default=None, help="only the first N dataset rows")
    ap.add_argument("--name", default="ws-refund-regression")
    ap.add_argument("--parallelism", type=int, default=4)
    ap.add_argument("--out", default=str(RESULTS), help="where to write the JSON results")
    args = ap.parse_args(argv)
    results_path = Path(args.out)

    instructions = Path(args.instructions).read_text()
    variant = Path(args.instructions).stem.replace("_instructions", "")

    @job("refund-agent")
    async def run_agent(dp: DataPoint, index: int) -> dict:
        # temperature 0: a regression gate wants the same answer for the same prompt as far as the
        # provider allows. Production keeps the default; this is an eval setting, not an app setting.
        body = {"temperature": 0,
                "orq": {"tags": ["workshop", "eval", variant],
                        "metadata": {"variant": variant, "expected": dp.inputs.get("expected_decision", "")}}}
        r = await asyncio.to_thread(chat, dp.inputs["message"], instructions=instructions, store=OrderStore(), extra_body=body)
        return {"answer": r.text, "tool_calls": r.tool_calls, "trace_id": r.trace_id}

    url_out: list[str] = []
    results = asyncio.run(evaluatorq(
        args.name,
        data=load_rows(args.limit),
        jobs=[run_agent],
        evaluators=EVALUATORS,
        parallelism=args.parallelism,
        print_results=True,
        description=f"instructions={Path(args.instructions).name}",
        _experiment_url_out=url_out,
    ))
    rows = rows_detail(results)
    scores = means(rows)
    url = url_out[0] if url_out else ""
    failed = [k for k, thr in THRESHOLDS.items() if scores.get(k, 0.0) < thr]

    payload = {
        "name": args.name, "instructions": args.instructions, "variant": variant,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"), "rows": len(rows),
        "scores": scores, "thresholds": THRESHOLDS, "failed": failed, "experiment_url": url, "details": rows,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2) + "\n")

    md = summary_md(args.name, args.instructions, scores, url, len(rows))
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md + "\n")
    print(f"wrote {results_path}")
    if failed:
        print(f"REGRESSION: {', '.join(failed)} below threshold")
        return 1
    print("OK: every scorer at or above its threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
