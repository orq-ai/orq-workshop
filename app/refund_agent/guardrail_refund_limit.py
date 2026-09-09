# Python guardrail: block when the assistant commits to a refund above the EUR 500 limit.
# orq calls evaluate(log). log["output"] is the model answer. Return True to pass, False to block.
import re

LIMIT = 500.0


NEGATED = re.compile(r"\b(cannot|can't|unable|not able|exceeds|above the limit|over the limit|human review)\b", re.I)


def evaluate(log):
    text = log.get("output") or ""
    if not re.search(r"\b(refund(ed)?|issued|processed)\b", text, re.I):
        return True
    if NEGATED.search(text):  # a policy-correct refusal that quotes the amount is not a promise
        return True
    for raw in re.findall(r"(?:EUR|€)\s?([0-9][0-9.,]*)", text):
        try:
            amount = float(raw.replace(",", ""))
        except ValueError:
            continue
        if amount > LIMIT:
            return False
    return True
