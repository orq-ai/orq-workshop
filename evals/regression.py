"""Quality regression gate: `uv run python -m evals.regression` (also `make eval`).

What it does: runs the local refund agent (`app.refund_agent.agent.chat`) over every row of
app/data/dataset.jsonl with evaluatorq, scores each row with the three scorers in
evals/scorers.py, and takes the mean pass rate per scorer.

What makes CI fail: any mean below its entry in THRESHOLDS exits 1. This is a regression
gate, not a benchmark. The thresholds say "no worse than the agent we shipped", they carry a
margin so the model's own variance does not flake a green PR, and they only move when someone
edits this file on purpose. Same code, same dataset, same scorers on every run: the only thing
a PR can change is the agent, so a drop is the PR's doing.

    python -m evals.regression                                              # fixed instructions
    python -m evals.regression --instructions app/data/vulnerable_instructions.md
    python -m evals.regression --limit 5                                    # quick local check

Every run is also an Experiment run in the Studio (evaluatorq reads ORQ_API_KEY from .env),
so a red run and a green run sit next to each other with per-row verdicts. The same detail
lands in evals/results/latest.json, and the markdown table goes to $GITHUB_STEP_SUMMARY in CI.
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
from app.refund_agent.config import (  # loads .env; evaluatorq reads ORQ_API_KEY at call time
    DATA_DIR,
    ROOT,
    settings,
)
from app.refund_agent.tools import OrderStore
from evals.scorers import EVALUATORS

# Calibrated on 2026-09-08 over the 20-row dataset (gpt-4o-mini): fixed instructions scored
# 0.85 / 1.00 / 0.70 and 0.90 / 1.00 / 0.75 in two runs, vulnerable ones 0.75 / 1.00 / 0.55.
# 2026-09-15, gpt-5.6-luna on the Responses API: fixed 0.95 / 1.00 / 0.90, vulnerable
# 0.80 / 0.90 / 0.60. The judge bar is 0.70, not 0.85: an LLM judge lands on the threshold often
# enough that a zero-margin gate would flake on green code.
THRESHOLDS = {"decision_matches": 0.80, "no_pii_leak": 1.00, "policy_judge": 0.70}
RESULTS = ROOT / "evals" / "results" / "latest.json"


def load_rows(limit: int | None = None) -> list[DataPoint]:
    """Read app/data/dataset.jsonl into evaluatorq DataPoints, optionally only the first N."""
    lines = (DATA_DIR / "dataset.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [
        DataPoint(inputs=row["inputs"], expected_output=row["expected_output"])
        for row in rows[:limit]
    ]


def rows_detail(results) -> list[dict]:
    """One record per dataset row: input, output and every scorer verdict with its explanation.

    A scorer that raised, or returned no score, counts as a fail: the gate must not go green
    because the judge was unreachable.
    """
    records = []
    for datapoint_result in results:
        for job_result in datapoint_result.job_results or []:
            if isinstance(job_result.output, dict):
                output = job_result.output
            else:
                output = {"answer": str(job_result.output)}
            scores = {}
            for score in job_result.evaluator_scores or []:
                passed = False
                if not score.error and score.score is not None:
                    if score.score.pass_ is not None:
                        passed = score.score.pass_
                    else:
                        passed = bool(score.score.value)
                explanation = score.error or getattr(score.score, "explanation", None) or ""
                scores[score.evaluator_name] = {
                    "pass": bool(passed),
                    "explanation": explanation[:300],
                }
            inputs = datapoint_result.data_point.inputs
            records.append(
                {
                    "message": inputs.get("message"),
                    "expected_decision": inputs.get("expected_decision"),
                    "tool_calls": output.get("tool_calls", []),
                    "answer": output.get("answer", ""),
                    "trace_id": output.get("trace_id"),
                    "error": str(datapoint_result.error or job_result.error or "") or None,
                    "scores": scores,
                }
            )
    return records


def means(rows: list[dict]) -> dict[str, float]:
    """Mean pass rate per scorer over the detail records. Errors and missing scores count as 0."""
    per_scorer: dict[str, list[float]] = {}
    for row in rows:
        for name, score in row["scores"].items():
            per_scorer.setdefault(name, []).append(1.0 if score["pass"] else 0.0)
    return {
        name: round(sum(values) / len(values), 3)
        for name, values in per_scorer.items()
        if values
    }


def summary_md(name: str, instructions: str, scores: dict[str, float], url: str, rows: int) -> str:
    """The scorer table as markdown, for the GitHub job summary ($GITHUB_STEP_SUMMARY)."""
    lines = [
        f"## Eval gate: {name}",
        "",
        f"Instructions: `{instructions}` · rows: {rows}",
        "",
        "| scorer | mean | threshold | status |",
        "|---|---|---|---|",
    ]
    for scorer, threshold in THRESHOLDS.items():
        mean = scores.get(scorer, 0.0)
        status = "PASS" if mean >= threshold else "FAIL"
        lines.append(f"| {scorer} | {mean:.2f} | {threshold:.2f} | {status} |")
    if url:
        lines += ["", f"Experiment: {url}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns 0 when every scorer is at or above its threshold, else 1."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--instructions", default=str(DATA_DIR / "fixed_instructions.md"))
    parser.add_argument("--limit", type=int, default=None, help="only the first N dataset rows")
    parser.add_argument("--name", default="ws-refund-regression")
    parser.add_argument("--parallelism", type=int, default=4)
    parser.add_argument("--out", default=str(RESULTS), help="where to write the JSON results")
    args = parser.parse_args(argv)
    results_path = Path(args.out)

    instructions = Path(args.instructions).read_text()
    variant = Path(args.instructions).stem.replace("_instructions", "")  # "fixed" or "vulnerable"

    # ── Step 1 · Run the agent over the dataset ──
    # One job per row: the local tool loop with the instructions under test and a fresh
    # OrderStore, so a refund issued on one row cannot leak into the next.
    @job("refund-agent")
    async def run_agent(datapoint: DataPoint, index: int) -> dict:
        # No temperature: GPT-5.x rejects it (400). The gate lives with the model's own variance,
        # which is why THRESHOLDS carry a margin. metadata is a top-level body field.
        body = {
            "metadata": {
                "variant": variant,
                "expected": datapoint.inputs.get("expected_decision", ""),
                "tag": "eval",
            }
        }
        result = await asyncio.to_thread(
            chat,
            datapoint.inputs["message"],
            instructions=instructions,
            store=OrderStore(),
            extra_body=body,
        )
        return {"answer": result.text, "tool_calls": result.tool_calls, "trace_id": result.trace_id}

    url_out: list[str] = []
    results = asyncio.run(
        evaluatorq(
            args.name,
            data=load_rows(args.limit),
            jobs=[run_agent],
            evaluators=EVALUATORS,
            parallelism=args.parallelism,
            print_results=True,
            description=f"instructions={Path(args.instructions).name}",
            path=settings.path,  # pin the Experiment to <project>/workshop; omitting this drops it in the workspace's Default project
            _experiment_url_out=url_out,
        )
    )

    # ── Step 2 · Score and compare with the thresholds ──
    # The mean per scorer is the number under test. A scorer is "failed" when its mean is
    # below the bar, and one failed scorer is enough to fail the gate.
    rows = rows_detail(results)
    scores = means(rows)
    url = url_out[0] if url_out else ""
    failed = [scorer for scorer, threshold in THRESHOLDS.items() if scores.get(scorer, 0.0) < threshold]

    # ── Step 3 · Write the results, print the verdict, return the exit code ──
    # The JSON keeps every row's verdicts for a post-mortem; the markdown table is what the
    # GitHub job summary shows; the block below is what a learner reads in the terminal.
    payload = {
        "name": args.name,
        "instructions": args.instructions,
        "variant": variant,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": len(rows),
        "scores": scores,
        "thresholds": THRESHOLDS,
        "failed": failed,
        "experiment_url": url,
        "details": rows,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2) + "\n")

    markdown = summary_md(args.name, args.instructions, scores, url, len(rows))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary_file:
            summary_file.write(markdown + "\n")

    print(f"── Quality gate · {args.name} ".ljust(55, "─"))
    print(f"prompt   : {Path(args.instructions).name} ({variant})")
    print(f"rows     : {len(rows)}")
    for scorer, threshold in THRESHOLDS.items():
        mean = scores.get(scorer, 0.0)
        status = "fail" if scorer in failed else "pass"
        print(f"{status:<8} : {scorer} {mean:.2f} (threshold {threshold:.2f})")
    print(f"results  : {results_path}")
    if url:
        print(f"studio   : {url}")
    if failed:
        print(f"verdict  : failed, {', '.join(failed)} below threshold (exit 1)")
        print("next     : open the Experiment run and read the per-row explanations of the red cells")
        return 1
    print("verdict  : passed, every scorer at or above its threshold (exit 0)")
    print("next     : open the Experiment run; each run sits next to the previous ones with per-row verdicts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
