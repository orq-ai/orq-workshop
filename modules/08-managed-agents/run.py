"""Module 08 starter: the refund agent as a managed orq Agent.

The agent ws-refund-agent already exists (`make seed`). Its tools are code tools, so orq runs the
loop and the tools: one Responses call per customer turn. Your job is the client side: invoke it
through the Responses API and read the tool calls from the output items, then the rest of the Run
Agents surface: variables and metadata, a second user turn, tool_choice, memory, versions. The
solution adds step 2b, the hybrid alternative with function tools that your own code runs.

Fill in the TODOs. The script runs as is; a step with an unfilled TODO says so in its output block.
Run it with `uv run python modules/08-managed-agents/run.py`. The solution is in solution/run.py.
"""

from __future__ import annotations

from typing import Any

from app.refund_agent.client import make_orq
from app.refund_agent.config import settings

AGENT = settings.key("refund-agent")   # ws-refund-agent
QUESTION = "Refund ord_a2 please, the dock does not fit."
orq = make_orq()


# ── Step 1 · Inspect the agent ──
# A GET returns tools as {action_type, id, key, requires_approval}; a create or update wants
# {"type": "code", "key": ...}. Read the shape before you write anything back.
def step_1_inspect() -> None:
    """Print the agent's model, limits and tools as the API returns them."""
    agent_info = orq.agents.retrieve(agent_key=AGENT).model_dump(by_alias=True)
    agent_settings = agent_info["settings"]

    print("── Step 1 · Inspect the agent ─────────────────────────")
    print(f"agent    : {agent_info['key']} v{agent_info['version']}")
    print(f"model    : {agent_info['model']['id']}")
    print(f"limits   : max_iterations {agent_settings['max_iterations']}")
    print(f"tools    : {[(tool['action_type'], tool.get('key', tool['display_name'])) for tool in agent_settings['tools']]}  (the READ shape)")
    # Writes use a different shape: [{"type": "code", "key": "ws-lookup_order"}, ...]. Never PATCH the GET body back.


def run_agent(agent: str, text: str, **kw: Any) -> dict[str, Any]:
    """One customer turn: one Responses call, orq runs the loop and the tools."""
    # TODO: response = orq.responses.create(model=f"agent/{agent}", input=text, **kw).model_dump(by_alias=True)
    #       then collect the name of every item in response["output"] whose type is "function_call"
    response: dict[str, Any] = {"output": [], "id": "", "telemetry": {"trace_id": ""}}
    called: list[str] = []
    text_out = " ".join(
        content["text"]
        for item in response["output"]
        if item["type"] == "message"
        for content in item["content"]
        if content["type"] == "output_text"
    )
    return {"text": text_out, "tool_calls": called, "traces": [response["telemetry"]["trace_id"]], "response_id": response["id"]}


# ── Step 2 · Invoke it ──
# One customer turn through run_agent. orq runs the tools, so the response already holds the
# function_call items and the final message; the trace shows each tool call.
def step_2_invoke() -> None:
    """Run one refund turn and print the tools the agent asked for."""
    out = run_agent(AGENT, QUESTION)

    print("── Step 2 · Invoke it ─────────────────────────────────")
    if not out["response_id"]:
        print("TODO     : fill in the Responses call in run_agent, then rerun")
    print(f"question : {QUESTION}")
    print(f"tools    : {' → '.join(out['tool_calls'])}")
    print(f"answer   : {out['text'][:80]!r}")
    print(f"next     : run `orq traces conversation {out['traces'][-1]}`")


# ── Step 3 · Stream ──
# stream=True returns events; text arrives as response.output_text.delta.
def step_3_stream() -> None:
    """Stream a reply the agent can give without a tool call."""
    print("── Step 3 · Stream ────────────────────────────────────")
    # TODO: the same call with stream=True; print the first response.output_text.delta events
    print("TODO     : fill in a stream=True call and print the first output_text.delta events, then rerun")


# ── Step 4 · Variables, metadata, identity, thread ──
# variables fill {{placeholders}} (here in the input), metadata is echoed and stored on the trace,
# identity and thread only land on the trace.
def step_4_variables() -> None:
    """One call carrying variables, metadata, identity and thread; print what comes back."""
    print("── Step 4 · Variables, metadata, identity, thread ─────")
    # TODO: orq.responses.create(model=f"agent/{AGENT}", input="My name is {{customer_name}}. Greet me by name in one sentence, nothing else.",
    #       variables={"customer_name": ...}, metadata={"session_id": ...}, identity={"id": settings.identity_id}, thread={"id": "conv-ws-1"})
    #       then print response.metadata, response.variables and response.telemetry.trace_id
    print("TODO     : fill in the call with variables, metadata, identity and thread, then rerun")


# ── Step 5 · Continue a conversation ──
# previous_response_id with a new user message continues the conversation; responses.get fetches
# any stored response; background=True returns status queued and get doubles as polling.
def step_5_continue() -> None:
    """A refund turn, then a follow-up question answered from context alone."""
    print("── Step 5 · Continue a conversation ───────────────────")
    first = run_agent(AGENT, QUESTION)
    # TODO: orq.responses.create(model=f"agent/{AGENT}", previous_response_id=first["response_id"], input="Thanks. What was the refund amount, digits only?")
    #       then orq.responses.get(response_id=<that id>) and compare the text
    print(f"turn 1   : {first['text'][:80]!r}" if first["text"] else "turn 1   : (empty until the run_agent TODO in step 2 is filled in)")
    print("TODO     : fill in the follow-up turn with previous_response_id and the responses.get call, then rerun")


# ── Step 6 · Control tool calls ──
# tool_choice: "none", "required", or {"type": "function", "name": "ws-get_policy"} (the tool key). A tools array in
# the request is ignored on agent/ calls.
def step_6_tool_choice() -> None:
    """Three calls with three tool_choice values; print the output item types of each."""
    print("── Step 6 · Control tool calls ────────────────────────")
    # TODO: for each choice, orq.responses.create(model=f"agent/{AGENT}", input=QUESTION, tool_choice=choice)
    #       and print [item["type"] for item in response.output]
    print("TODO     : fill in the three tool_choice calls, then rerun")


# ── Step 7 · Memory ──
# Memory goes on a copy of the agent: once an agent has memory tools, every call needs memory.entity_id.
def step_7_memory() -> None:
    """Two turns on a memory-enabled copy of the agent, same entity id."""
    print("── Step 7 · Memory ────────────────────────────────────")
    # TODO: memory store ws_refund_memory + a copy of the agent with memory tools; two calls with memory={"entity_id": ...}
    print("TODO     : fill in the memory store, the agent copy and the two turns, then rerun")


# ── Step 8 · Versions and @version routing ──
# A minor version bump publishes a version; agent/<key>@<version> pins it.
def step_8_versions() -> None:
    """Publish a version and call the agent pinned to each version."""
    print("── Step 8 · Versions and @version routing ─────────────")
    # TODO: orq.agents.update(agent_key=AGENT, ..., version_increment="minor", version_description="...")
    #       then invoke agent/ws-refund-agent@1.0.0, @1.1.0, @latest, @production
    print("TODO     : fill in the version bump and the four pinned calls, then rerun")


if __name__ == "__main__":
    step_1_inspect()
    step_2_invoke()
    step_3_stream()
    step_4_variables()
    step_5_continue()
    step_6_tool_choice()
    step_7_memory()
    step_8_versions()
