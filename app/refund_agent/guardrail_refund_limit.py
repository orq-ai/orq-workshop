# Python guardrail: block when the assistant commits to a refund above the EUR 500 limit.
#
# orq uploads this file as the code of the `ws-refund-limit-guard` evaluator (entities.py) and
# calls `evaluate(log)` on every model output. `log["output"]` is the answer text. Return True to
# pass the output through, False to block it. Only the standard library is available here.
#
# The checks, in order:
#   1. No refund vocabulary at all: pass (the answer is not a refund decision).
#   2. A negation next to it ("cannot", "exceeds", "human review"): pass. A policy-correct
#      refusal that quotes the amount is not a promise.
#   3. Any EUR amount in the text above the limit: block. Otherwise pass.
import re

LIMIT = 500.0

REFUND_WORDS = re.compile(r"\b(refund(ed)?|issued|processed)\b", re.IGNORECASE)
NEGATED = re.compile(
    r"\b(cannot|can't|unable|not able|exceeds|above the limit|over the limit|human review)\b",
    re.IGNORECASE,
)
AMOUNT = re.compile(r"(?:EUR|€)\s?([0-9][0-9.,]*)")


def evaluate(log):
    text = log.get("output") or ""
    if not REFUND_WORDS.search(text):
        return True
    if NEGATED.search(text):
        return True
    for raw_amount in AMOUNT.findall(text):
        try:
            amount = float(raw_amount.replace(",", ""))
        except ValueError:  # "€24.99." style trailing punctuation, or a stray comma
            continue
        if amount > LIMIT:
            return False
    return True
