Work through the tracing module with me. Read AGENTS.md, app/refund_agent/agent.py, app/refund_agent/tracing.py and modules/tracing/run.py first.

Each of the five steps in modules/tracing/run.py has exactly one line marked `# CHANGE:`. For each step in order: make that one change and nothing else, run `uv run python modules/tracing/run.py`, and show me the step's output block. Stop after each step and tell me what changed in the output and what to look for in the orq.ai Studio. Step 4 needs `uv sync --extra langgraph` first.

When all five are done, use the orq.ai MCP tools (`list_traces`, `list_spans`) to fetch the spans of the newest trace named `refund_turn` and tell me the order of tool spans and model calls inside it. Do not change anything under app/.
