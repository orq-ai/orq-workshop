"""make traffic: 20 conversations through the gateway, so Traces has something to analyse.

What: every row of `app/data/dataset.jsonl` (or the first N) sent as one refund turn.
Why: failure analysis (module 07) needs real policy violations to find. Even rows run with the
fixed instructions, odd rows with the vulnerable ones. Each call carries an identity and a thread
id, so traces group per customer and per conversation.
How: `make traffic`, or `uv run python -m app.traffic 6` for the first six rows. Filter the
traces afterwards on `metadata.batch` (this run) or `metadata.tag == "traffic"` (every run).
"""

from __future__ import annotations

import json
import sys
import uuid

from app.refund_agent.agent import chat
from app.refund_agent.config import DATA_DIR, settings


def main(limit: int = 20) -> None:
    """Send `limit` dataset rows as single turns and print one table row per conversation."""
    dataset_lines = (DATA_DIR / "dataset.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in dataset_lines if line.strip()][:limit]
    vulnerable_instructions = (DATA_DIR / "vulnerable_instructions.md").read_text()
    batch = uuid.uuid4().hex[:8]  # short random id shared by every trace of this run

    # ── Step 1 · Send the conversations ──
    # One turn per row, alternating fixed and vulnerable instructions. A failed call is printed
    # to stderr and the loop goes on: a failed call leaves a trace too.
    print("── Step 1 · Send the conversations ────────────────────")
    print(f"{'#':<3}{'variant':<11}{'expected':<13}{'trace':<32} tools")
    for i, row in enumerate(rows):
        variant = "fixed" if i % 2 == 0 else "vulnerable"
        instructions_override = {} if variant == "fixed" else {"instructions": vulnerable_instructions}
        expected = row["inputs"]["expected_decision"]
        # identity, thread, metadata and name are top-level body fields (not nested under "orq")
        extra_body = {
            "name": "refund-traffic",
            "identity": {"id": f"customer-user_00{1 + i % 3}"},  # three customers take turns
            "thread": {"id": f"traffic-{batch}-{i:02d}"},
            "metadata": {
                "variant": variant,
                "expected": expected,
                "batch": batch,
                "tag": "traffic",
                "index": f"{i:02d}",
            },
            # A `reasoning` output item (any effort above none, when the model actually reasons) makes the
            # trace store drop the whole output: search has no gen_ai.output, the thread view prints
            # "[content unavailable]". The traffic runs without reasoning so module 07 can read the answers.
            "reasoning": {"effort": "none"},
        }
        try:
            result = chat(row["inputs"]["message"], extra_body=extra_body, **instructions_override)
            print(f"{i:02d} {variant:10s} {expected:12s} {result.trace_id} {' → '.join(result.tool_calls)}")
        except Exception as exc:  # noqa: BLE001  keep going, a failed call is also a trace
            print(f"{i:02d} {variant:10s} ERROR {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)

    # ── Step 2 · Find the batch in the Studio ──
    # Every trace of this run carries the same metadata.batch, so one filter shows them all.
    print("── Step 2 · Find the batch in the Studio ──────────────")
    print(f"batch    : {batch}")
    print(f"rows     : {len(rows)}")
    print(f"next     : filter traces by metadata.batch = {batch} in {settings.base_url}/traces")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
