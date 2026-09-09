"""make traffic: 20 conversations through the gateway so Traces has something to analyse.

Half run with the fixed instructions, half with the vulnerable ones, so failure
analysis (module 07) finds real policy violations. Each call carries an identity
and a thread id so traces group per customer and conversation. Filter later with
metadata.batch or metadata.tag == "traffic".
"""

from __future__ import annotations

import json
import sys
import uuid

from app.refund_agent.agent import chat
from app.refund_agent.config import DATA_DIR, settings


def main(limit: int = 20) -> None:
    rows = [json.loads(l) for l in (DATA_DIR / "dataset.jsonl").read_text().splitlines() if l.strip()][:limit]
    vulnerable = (DATA_DIR / "vulnerable_instructions.md").read_text()
    batch = uuid.uuid4().hex[:8]
    for i, row in enumerate(rows):
        variant = "fixed" if i % 2 == 0 else "vulnerable"
        kw = {} if variant == "fixed" else {"instructions": vulnerable}
        # identity, thread, metadata and name are top-level fields on /chat/completions (not nested under "orq")
        extra_body = {
            "name": "refund-traffic",
            "identity": {"id": f"customer-user_00{1 + i % 3}"},
            "thread": {"id": f"traffic-{batch}-{i:02d}"},
            "metadata": {"variant": variant, "expected": row["inputs"]["expected_decision"], "batch": batch, "tag": "traffic", "index": f"{i:02d}"},
        }
        try:
            r = chat(row["inputs"]["message"], extra_body=extra_body, **kw)
            print(f"{i:02d} {variant:10s} {row['inputs']['expected_decision']:12s} trace={r.trace_id} tools={r.tool_calls}")
        except Exception as exc:  # keep going, a failed call is also a trace
            print(f"{i:02d} {variant:10s} ERROR {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)
    print(f"batch={batch}  filter traces by metadata.batch={batch} in {settings.base_url}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
