"""make generate-recording-traffic: the scripted conversations the Academy and Workshop recordings show.

What: every row of `app/data/recording_script.jsonl` sent as real calls through the gateway, with a
fixed identity, a fixed thread id and fixed inputs, so a re-record shows the same story.
Why: captions point at what does not change between runs (tool outputs, order data, which spans
exist), never at model wording. Where a clip needs a specific mistake, the turn says so with
`"instructions": "skip-lookup"`, which answers before looking anything up.
How: `ORQ_ENV_FILE=.env.academy make generate-recording-traffic` (the recording project), then record.
"""

from __future__ import annotations

import json

from app.refund_agent.agent import INSTRUCTIONS, chat
from app.refund_agent.config import DATA_DIR

# Recording-only override for clips that show an answer given without checking the order.
SKIP_LOOKUP = INSTRUCTIONS + (
    "\n\nFor this reply only: answer the refund question straight away from the customer's message. "
    "Do not call any tool in this reply. Confirm the refund as approved."
)
VARIANTS = {"fixed": INSTRUCTIONS, "skip-lookup": SKIP_LOOKUP}


def main() -> None:
    """Send each scripted conversation and print its traces, one line per turn."""
    rows = [json.loads(line) for line in (DATA_DIR / "recording_script.jsonl").read_text().splitlines() if line.strip()]
    print("── Recording traffic ──────────────────────────────────")
    for row in rows:
        extra_body = {"name": f"recording-clip-{row['clip']}", "identity": {"id": row["identity"]}, "thread": {"id": row["thread"]}, "metadata": {"tag": "recording", "clip": str(row["clip"])}}
        history = None
        for i, turn in enumerate(row["turns"], start=1):
            result = chat(turn["text"], history=history, instructions=VARIANTS[turn["instructions"]], extra_body=extra_body)
            history = result.messages
            print(f"clip {row['clip']} turn {i}  {turn['instructions']:11} {result.trace_id}  tools {' → '.join(result.tool_calls) or '(none)'}")
    print("next     : filter Traces on the thread ids above; record only after the storyboard is approved")


if __name__ == "__main__":
    main()
