"""make smoke: one refund turn through the gateway. Prints the answer and the trace id."""

from app.refund_agent.agent import chat
from app.refund_agent.config import settings


def main() -> None:
    settings.require_key()
    result = chat("Hi, I want a refund for order ord_a1, I changed my mind.")
    print(f"model      : {settings.model}")
    print(f"tool calls : {result.tool_calls}")
    print(f"answer     : {result.text}")
    print(f"trace id   : {result.trace_id}")
    print(f"open       : {settings.base_url}/traces  (search the trace id)")
    assert result.trace_id, "no x-orq-trace-id header: the call did not go through the orq gateway"
    assert "lookup_order" in result.tool_calls, "the model did not call lookup_order"
    print("OK")


if __name__ == "__main__":
    main()
