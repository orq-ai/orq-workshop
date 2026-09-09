# Cheat sheet

## URLs

| What | URL |
|---|---|
| OpenAI-compatible gateway | `https://my.orq.ai/v3/router` (`/chat/completions`, `/responses`, `/embeddings`, ...) |
| Anthropic-compatible gateway | `https://my.orq.ai/v3/anthropic` |
| OTLP traces | `https://my.orq.ai/v2/otel/v1/traces` with `Authorization: Bearer $ORQ_API_KEY` |
| Orq MCP server (coding agents) | `https://my.orq.ai/v2/mcp` |
| MCP Gateway (your tools) | `https://my.orq.ai/v3/mcp/<gateway-key>` |
| REST API | `https://my.orq.ai/v2/...` |

## CLI

```bash
orq auth login                 # browser sign-in
orq setup --local              # mint a project key into ./.env, optionally wire coding agents
orq doctor                     # health check
orq status / orq switch        # active workspace and project
orq launch claude|opencode|pi|codex [-p "prompt"]   # agent through the gateway, session only
orq connect --local [--dry-run|--status]            # permanent wiring for this project
orq chat create --model openai/gpt-4o-mini --messages '[{"role":"user","content":"hi"}]'
orq traces search --from 1h --to now   # recent traces; add --json
orq traces thread <trace_id>   # readable transcript
orq agents list | get <key> | invoke <key>
orq knowledge-bases search <id> --query "..."
orq mcp-gateways list-tools <key>
orq budgets list               # needs a Management Key
orq pii redact --text "..."
orq request GET /v2/routing-rules   # raw escape hatch for anything without a command
orq orqi "why did my agent fail today?"
```

## Python

```python
from openai import OpenAI
client = OpenAI(api_key=ORQ_API_KEY, base_url="https://my.orq.ai/v3/router")
client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[...],
    extra_body={
        "fallbacks": [{"model": "anthropic/claude-haiku-4-5"}],
        "retry": {"count": 2, "on_codes": [429, 500, 502, 503]},
        "cache": {"type": "exact_match", "ttl": 600},
        "plugins": [{"id": "pii_redaction", "language": "en"}],
        "guardrails": [{"id": "<evaluator_id>", "execute_on": "output"}],
        "name": "refund-turn", "identity": {"id": "customer-42"}, "thread": {"id": "conv-1"}, "metadata": {"tier": "free"},   # top-level, not under "orq"
    },
)

from orq_ai_sdk import Orq
orq = Orq(api_key=ORQ_API_KEY)
orq.responses.create(model="agent/<key>", input="...", memory={"entity_id": "customer-42"})
orq.knowledge.search(knowledge_id=..., query="...", search_type="hybrid_search", rerank_config={"model": "cohere/rerank-multilingual-v3.0"})
orq.traces.search(from_="1h")
orq.annotations.create(trace_id=..., span_id=..., annotations=[{"key": "rating", "value": 1}])
```

## Makefile

```bash
make setup doctor smoke test    # day 0
make seed                       # every prerequisite entity, idempotent
make traffic                    # 20 traced conversations for failure analysis
make m01 ... make m13           # run a module's solution
make eval                       # regression gate, exit 1 on failure
make redteam-gate               # static red team gate
make reset                      # delete everything with WS_PREFIX
make docs-serve slides          # docs site, deck
```
