"""make smoke: one refund turn through the orq gateway. The first thing a learner runs.

What: the same `chat()` every module uses, called once with a change-of-mind refund request.
Why: if this passes, the environment, the key in `.env`, the app and the gateway all work. The
trace id is the proof that the call went through orq and not straight to a provider.
How: `make smoke` (or `uv run python -m app.smoke`). Exits non-zero when a check fails.
"""

from app.refund_agent.agent import chat
from app.refund_agent.config import settings

QUESTION = "Hi, I want a refund for order ord_a1, I changed my mind."


def main() -> None:
    """Run one turn, print what happened, then check the two things that prove the setup works."""
    settings.require_key()  # stops here with a readable message when ORQ_API_KEY is empty

    # ── Step 1 · One refund turn through the gateway ──
    # The model looks the order up (and usually reads the policy), the app runs each tool locally,
    # and the gateway sets an x-orq-trace-id header on every response. Everything is printed
    # before the checks, so a failing check still shows what came back.
    result = chat(QUESTION)

    print("── Step 1 · One refund turn through the gateway ───────")
    print(f"model    : {settings.model}")
    print(f"question : {QUESTION}")
    print(f"answer   : {result.text[:100]}…")
    print(f"tools    : {' → '.join(result.tool_calls)}")
    print(f"trace    : {result.trace_id}")

    # No trace id means the client did not talk to orq: check ORQ_BASE_URL in .env.
    assert result.trace_id, "no x-orq-trace-id header: the call did not go through the orq gateway"
    # No lookup_order means the model answered without its tools: check MODEL and the instructions.
    assert "lookup_order" in result.tool_calls, "the model did not call lookup_order"

    print("verdict  : OK, the call went through orq and the model called lookup_order")
    print(f"next     : search the trace id in {settings.base_url}/traces; expect the last model call with cost, tokens and latency")


if __name__ == "__main__":
    main()
