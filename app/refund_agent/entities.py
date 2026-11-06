"""Idempotent create and delete of every orq entity the workshop uses.

What: one `ensure_*` function per entity kind (dataset, knowledge base, evaluators, tools, agents,
notifier, alert, annotation queue, webhook). Each one looks for its key first and only creates
what is missing, so a module can call it on every run. `seed` creates everything at once for
latecomers; `reset` deletes everything this repo created.

Why a prefix: every key starts with WS_PREFIX (`ws-refund-agent`; `ws_...` for memory stores,
whose keys reject hyphens), so `reset` can find the workshop's entities in a shared workspace and
leave everything else alone.

Why REST in places: the orq SDK (4.17 retested, 4.14 for the admin-only calls) cannot serialize or parse a few payloads. Each raw call below
says which quirk it works around, and goes through `rest_post`, `rest_get` or `rules_api`.

    uv run python -m app.refund_agent.entities seed
    uv run python -m app.refund_agent.entities reset
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from .client import make_orq
from .config import DATA_DIR, settings

K = settings.key  # K("refund-agent") -> "ws-refund-agent"

KB_CHUNK_SIZE = 300  # characters per chunk: one policy paragraph, roughly
KB_CHUNK_OVERLAP = 40  # so a sentence cut at a chunk border is still whole in one of the two


# ---------------------------------------------------------------- datasets


def ensure_dataset(
    orq=None, name: str = "refund-eval", rows: Path | None = DATA_DIR / "dataset.jsonl"
) -> str:
    """Create the dataset `K(name)` and fill it from a JSONL file. Returns the dataset id.

    Idempotency key: `display_name`. An existing dataset with rows is returned as is; an existing
    *empty* one (a seed that failed after creating it) is filled when `rows` is given.
    `rows=None` creates an empty dataset (the annotation-queues module fills `ws-review-dataset` from reviewed traces).
    """
    orq = orq or make_orq()
    key = K(name)
    points = [] if rows is None else [json.loads(line) for line in rows.read_text().splitlines() if line.strip()]
    # search=: a shared workspace holds far more than one page of datasets (one per seat, at least).
    for dataset in orq.datasets.list(limit=100, search=key).data or []:
        if dataset.display_name == key:
            if points and not orq.datasets.list_datapoints(dataset_id=dataset.id, limit=1).data:
                orq.datasets.create_datapoint(dataset_id=dataset.id, request_body=points)
            return dataset.id
    created = orq.datasets.create(display_name=key, path=settings.path)
    if points:
        orq.datasets.create_datapoint(dataset_id=created.id, request_body=points)
    return created.id


# ---------------------------------------------------------------- knowledge base


def ensure_knowledge_base(
    orq=None, name: str = "refund-policy", docs: Path = DATA_DIR / "kb"
) -> str:
    """Create the KB, one datasource per policy file, chunked with the Chunking API. Returns the KB id.

    Idempotency key: the KB `key`. An existing KB is returned without re-uploading chunks.
    """
    orq = orq or make_orq()
    key = K(name)
    for knowledge_base in orq.knowledge.list(limit=100).data or []:
        if knowledge_base.key == key:
            return knowledge_base.id
    knowledge_base = orq.knowledge.create(
        request={
            "key": key,
            "embedding_model": settings.embedding_model,
            "path": settings.path,
            "description": "Lumen Goods refund policy (workshop)",
        }
    )
    for doc_path in sorted(docs.glob("*.md")):
        datasource = orq.knowledge.create_datasource(
            knowledge_id=knowledge_base.id, display_name=doc_path.name
        )
        chunked = orq.chunking.parse(
            request={
                "text": doc_path.read_text(),
                "strategy": "recursive",
                "chunk_size": KB_CHUNK_SIZE,
                "chunk_overlap": KB_CHUNK_OVERLAP,
            }
        )
        orq.knowledge.create_chunks(
            knowledge_id=knowledge_base.id,
            datasource_id=datasource.id,
            request_body=[
                {"text": chunk.text, "metadata": {"topic": doc_path.stem}}
                for chunk in chunked.chunks
            ],
        )
    return knowledge_base.id


def ensure_external_knowledge_base(
    orq=None, name: str = "refund-policy-ext", api_url: str | None = None, api_key: str | None = None
) -> str:
    """An external KB: orq POSTs the search request to `api_url` itself (here `<edge>/search`), Bearer `api_key`.

    Idempotency key: the KB `key`. REST, not the SDK: `knowledge.create` in 4.14 has no `type` /
    `external_config`. Re-pointed when the URL changes (a new tunnel), so the key stays stable
    across sessions.
    """
    orq = orq or make_orq()
    key = K(name)
    base_url = (api_url or settings.edge_url).rstrip("/")
    if not base_url:
        raise RuntimeError("WS_EDGE_URL is not set: nothing public for orq to call")
    api_url = base_url + "/search"
    api_key = api_key or settings.webhook_secret
    body = {
        "key": key,
        "path": settings.path,
        "type": "external",
        "description": "Lumen Goods refund policy served by app/edge.py (workshop)",
        "external_config": {"name": "lumen-policy", "api_url": api_url, "api_key": api_key},
    }
    for knowledge_base in orq.knowledge.list(limit=100).data or []:
        if knowledge_base.key == key:
            rules_api(
                "PATCH",
                f"/v2/knowledge/{knowledge_base.id}",
                {"external_config": body["external_config"]},
            )
            return knowledge_base.id
    created = rest_post(None, "/v2/knowledge", body)
    return created.get("id") or created.get("_id")


# ---------------------------------------------------------------- evaluators


def ensure_python_guardrail(orq=None, name: str = "refund-limit-guard") -> str:
    """Blocks any assistant output that promises a refund above the EUR 500 limit. Returns the evaluator id.

    Idempotency key: the evaluator `key`. The code is `guardrail_refund_limit.py`, uploaded as is.
    """
    orq = orq or make_orq()
    key = K(name)
    existing = _find_eval(orq, key)
    if existing:
        return existing
    code = (Path(__file__).parent / "guardrail_refund_limit.py").read_text()
    # ponytail: REST, not orq.evals.create. The SDK's python_eval union lacks the `mode` discriminator (4.14.x).
    created = rest_post(
        orq,
        "/v2/evaluators",
        {
            "type": "python_eval",
            "key": key,
            "description": "Fail when the output commits to refunding more than EUR 500.",
            "path": settings.path,
            "code": code,
            "output_type": "boolean",  # without it the evaluator is stored as number and every guardrail call 502s
            "guardrail_config": {"enabled": True, "type": "boolean", "value": True},
        },
    )
    return created.get("id") or created.get("_id") or _find_eval(orq, key)


# The chat's Guardrails dropdown: choice -> (metadata.channel the chat sends, guardrails the rule applies).
# The python guardrail id is looked up when the rule is created, so it is named here by a marker.
CHAT_CHANNELS = {
    "pii": K("chat-pii"),
    "refund": K("chat-refund"),
    "both": K("chat-guarded"),
}
CHAT_GUARDED = CHAT_CHANNELS["both"]
_CHAT_RULE_GUARDRAILS = {
    "pii": ["pii"],
    "refund": ["refund"],
    "both": ["pii", "refund"],
}


def ensure_chat_guardrail_rule(orq=None, choice: str = "both") -> str:
    """The rule behind one option of the chat's Guardrails dropdown. Returns the rule id.

    Request-level `guardrails` are ignored on `/v3/router/responses`; rules apply to both
    endpoints. Each rule matches `metadata["channel"] == CHAT_CHANNELS[choice]`, which the chat
    sends only for that option: PII blocked on input (`pii`), the refund-limit guardrail on
    output (`refund`), or both. Idempotency key: the rule's display name.
    """
    orq = orq or make_orq()
    channel = CHAT_CHANNELS[choice]
    rule_name = K("guardrail-rule-chat" if choice == "both" else f"guardrail-rule-chat-{choice}")
    # Workspace-wide on purpose: a project-scoped rule only matches calls that carry a project, and
    # a workspace key carries none. The `metadata.channel` test keeps other traffic out of it.
    for rule in rules_api("GET", "/v2/guardrail-rules?limit=100").get("data") or []:
        if rule["display_name"] == rule_name:
            return rule.get("_id") or rule.get("id")
    guardrails = {
        "pii": lambda: {"id": "orq_pii_detection", "execute_on": "input"},
        "refund": lambda: {"id": ensure_python_guardrail(orq), "execute_on": "output"},
    }
    body: dict[str, Any] = {
        "display_name": rule_name,
        "description": f"Chat Guardrails dropdown ({choice}): calls tagged channel={channel}",
        "enabled": True,
        "expression": {"cel": f'metadata["channel"] == "{channel}"'},
        "guardrails": [guardrails[g]() for g in _CHAT_RULE_GUARDRAILS[choice]],
    }
    created = rules_api("POST", "/v2/guardrail-rules", body)
    created = created.get("guardrail_rule", created)
    return created.get("_id") or created.get("id")


def ensure_llm_judge(orq=None, name: str = "refund-policy-judge") -> str:
    """Binary judge: did the assistant follow the refund policy? Returns the evaluator id.

    Idempotency key: the evaluator `key`. The prompt is `app/data/judge_prompt.md`. Created with
    the SDK. `guardrail_config.enabled` is False: this evaluator scores, it does not block.
    """
    orq = orq or make_orq()
    key = K(name)
    existing = _find_eval(orq, key)
    if existing:
        return existing
    prompt = (DATA_DIR / "judge_prompt.md").read_text()
    evaluator = orq.evals.create(
        request={
            "type": "llm_eval",
            "key": key,
            "description": "Pass when the refund decision matches policy, fail otherwise.",
            "path": settings.path,
            "prompt": prompt,
            "model": settings.judge_model,
            "mode": "single",
            "output_type": "boolean",
            "guardrail_config": {"enabled": False, "type": "boolean", "value": True},
        }
    )
    return evaluator.id


def rest_post(orq, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Raw POST with the same credentials, for the few endpoints the SDK cannot serialize.

    `orq` is unused; it stays in the signature because callers pass it.
    """
    import httpx

    response = httpx.post(
        f"{settings.base_url}{path}",
        json=body,
        headers={"Authorization": f"Bearer {settings.bearer()}"},
        timeout=60,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"POST {path} -> {response.status_code}: {response.text[:300]}")
    body = response.json()
    return body.get("document", body)  # some endpoints wrap the entity


def _find_eval(orq, key: str) -> str | None:
    """The id of the evaluator with this exact key, or None. `search` is a substring match, hence the check."""
    for evaluator in orq.evals.all(limit=50, search=key).data or []:
        if getattr(evaluator, "key", None) == key:
            return getattr(evaluator, "id", None) or evaluator.model_dump().get("_id")
    return None


# ---------------------------------------------------------------- tools


def ensure_tools(orq=None) -> list[str]:
    """Register the three function tools as Tool entities. Agents reference them by key.

    Idempotency key: the tool `key` (`ws-lookup-order`, ...). Existing tools are skipped, not
    updated. Returns every key, created or not, in TOOL_SCHEMAS order.
    """
    from .tools import TOOL_SCHEMAS

    orq = orq or make_orq()
    existing = {
        tool.key for tool in (orq.tools.list(limit=100).data or []) if getattr(tool, "key", None)
    }
    keys = []
    for schema in TOOL_SCHEMAS:
        function = schema["function"]
        key = K(function["name"].replace("_", "-"))  # tool keys use hyphens, function names underscores
        keys.append(key)
        if key in existing:
            continue
        orq.tools.create(
            request={
                "type": "function",
                "key": key,
                "path": settings.path,
                "description": function["description"],
                "function": {
                    "name": function["name"],
                    "description": function["description"],
                    "parameters": function["parameters"],
                },
            }
        )
    return keys


# ---------------------------------------------------------------- agents


def agent_payload(
    variant: str = "fixed",
    knowledge_base_id: str | None = None,
    memory_store_id: str | None = None,
    tool_keys: list[str] | None = None,
    tool_kind: str = "code",
) -> dict[str, Any]:
    """The `agents.create` body for one instruction variant (`app/data/<variant>_instructions.md`).

    `tool_kind="code"` (the default) gives the agent remote Python tools: orq runs the loop AND
    the tools, one Responses call per turn. `"function"` gives it function tools: orq runs the
    model and your code runs the tools (the hybrid method, the managed-agents module step 2b). Pure apart from
    `ensure_code_tools()` / `ensure_tools()` when `tool_keys` is not given. The fixed code agent
    is keyed `ws-refund-agent`, every other one `ws-refund-agent-<variant>`, and a function-tool
    agent adds `-function`.
    """
    instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
    if tool_keys is None:
        tool_keys = ensure_code_tools() if tool_kind == "code" else ensure_tools()
    tools: list[dict[str, Any]] = [{"type": tool_kind, "key": tool_key} for tool_key in tool_keys]
    key = K("refund-agent" if variant == "fixed" else f"refund-agent-{variant}")
    model: Any = settings.model
    if tool_kind == "code":
        # The model sees a code tool's key as its name, so say which names exist.
        instructions += "\n\nYour tools are named " + ", ".join(tool_keys) + "."
        model = {"id": settings.model, "parameters": {"reasoning_effort": "none"}}
    else:
        key += "-function"
    payload: dict[str, Any] = {
        "key": key,
        "display_name": f"Refund agent ({variant}{', function tools' if tool_kind == 'function' else ''})",
        "role": "Customer-service refund agent for Lumen Goods.",
        "description": "Handles refund requests for authenticated retail customers. Tools: lookup_order, get_policy, issue_refund.",
        "instructions": instructions,
        "path": settings.path,
        "model": model,
        "settings": {"max_iterations": 8, "max_execution_time": 120, "tools": tools},
    }
    if knowledge_base_id:
        payload["knowledge_bases"] = [{"knowledge_id": knowledge_base_id}]
        # An attached KB is never searched unless the agent also has the two built-in KB tools.
        tools.extend([{"type": "retrieve_knowledge_bases"}, {"type": "query_knowledge_base"}])
    if memory_store_id:
        payload["memory_stores"] = [{"memory_store_id": memory_store_id}]
    return payload


def ensure_agent(orq=None, variant: str = "fixed", **kw: Any) -> str:
    """Create the refund agent for one instruction variant. Returns the agent key.

    Idempotency key: the agent `key` from `agent_payload`. An existing agent is left as is, even
    if its instructions or tools differ. Extra keyword arguments go to `agent_payload`.
    """
    orq = orq or make_orq()
    payload = agent_payload(variant, **kw)
    try:
        orq.agents.retrieve(agent_key=payload["key"])
        return payload["key"]
    except Exception:
        pass  # not found (or not readable): create it below
    orq.agents.create(**payload)
    return payload["key"]


def hosted_tool_code(name: str) -> str:
    """Python for the orq code tool `name`: only what that tool needs from tools.py, inlined.

    orq runs it with the call's arguments in `params` and returns whatever it leaves in `result`.
    The function bodies are copied from tools.py, so the business rules have one source; the
    orders and the policy texts are written out one entry per line, readable in the Studio.
    ponytail: a fresh OrderStore per call, so a refund is not remembered between calls (only
    ord_a4, refunded in the fixture, answers already_refunded); persisting needs an external store.
    """
    import inspect

    from . import tools

    header = (
        f"# {name}: orq code tool, generated by `make seed-workspace` from app/refund_agent/tools.py.\n"
        "# orq passes the call's arguments in `params` and returns what is left in `result`."
    )
    if name != "get_policy":
        header += "\n# Every call starts from the orders below: a refund is not remembered between calls."
    # No `from __future__` import: orq prepends its own code, so it would not be first.
    imports = "from copy import deepcopy\nfrom typing import Any"
    fixture = "_FIXTURE = {\n" + "".join(  # one order per line
        f"    {key!r}: [\n" + "".join(f"        {row!r},\n" for row in value) + "    ],\n"
        if isinstance(value, list)
        else f"    {key!r}: {value!r},\n"
        for key, value in tools._FIXTURE.items()
    ) + "}"
    store = inspect.getsource(tools.OrderStore)
    if name == "lookup_order":
        parts = [
            imports,
            f"WINDOW_DAYS = {tools.WINDOW_DAYS!r}",
            fixture,
            store,
            inspect.getsource(tools.lookup_order),
            "result = lookup_order(OrderStore(), **params)",
        ]
    elif name == "issue_refund":
        parts = [
            imports,
            (
                f"WINDOW_DAYS = {tools.WINDOW_DAYS!r}\n"
                f"REFUND_LIMIT_EUR = {tools.REFUND_LIMIT_EUR!r}\n"
                f"POST_WINDOW_REASONS = {tools.POST_WINDOW_REASONS!r}"
            ),
            fixture,
            store,
            inspect.getsource(tools.issue_refund),
            "result = issue_refund(OrderStore(), **params)",
        ]
    else:  # get_policy: the policy files as strings, the same answers as tools.get_policy
        texts = {topic: (tools.KB_DIR / f"{topic}.md").read_text() for topic in tools.POLICY_TOPICS}
        assert not any('"""' in t or "\\" in t for t in texts.values()), "policy text breaks the quoting"
        policy = "\n".join(f'    {topic!r}: """{text}""",' for topic, text in texts.items())
        parts = [
            f"POLICY_TOPICS = {tools.POLICY_TOPICS!r}",
            f"POLICY = {{\n{policy}\n}}",
            (
                "def get_policy(topic):\n"
                "    if topic not in POLICY:\n"
                "        return {'ok': False, 'error': 'unknown_topic', 'topics': list(POLICY_TOPICS)}\n"
                "    return {'ok': True, 'topic': topic, 'text': POLICY[topic], 'source': 'orq_code_tool'}"
            ),
            "result = get_policy(**params)",
        ]
    return "\n\n\n".join([header, *parts]) + "\n"


def ensure_code_tools(orq=None) -> list[str]:
    """Register the three refund tools as orq code tools: remote Python that orq runs. Returns the keys.

    Idempotency key: the tool `key` (`ws-lookup_order`, ...; the model sees the key as the tool
    name). Existing tools are skipped. An agent that references them runs its loop AND its tools
    in orq, so evaluatorq's built-in `agent:<key>` target drives it with no adapter.
    """
    from .tools import TOOL_SCHEMAS

    orq = orq or make_orq()
    existing = {
        tool.key for tool in (orq.tools.list(limit=100).data or []) if getattr(tool, "key", None)
    }
    tool_keys = []
    for schema in TOOL_SCHEMAS:
        function = schema["function"]
        key = K(function["name"])  # the model sees the key as the tool name
        tool_keys.append(key)
        if key in existing:
            continue
        # The gateway calls code tools in strict mode: every property required, no `default`,
        # additionalProperties false; otherwise the agent call is a 400 invalid_function_parameters.
        properties = {
            name: {k: v for k, v in spec.items() if k != "default"}
            for name, spec in function["parameters"]["properties"].items()
        }
        parameters = {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
        orq.tools.create(
            request={
                "type": "code",
                "key": key,
                "path": settings.path,
                "description": function["description"],
                "code_tool": {
                    "language": "python",
                    "code": hosted_tool_code(function["name"]),
                    "parameters": parameters,
                },
            }
        )
    return tool_keys


def ensure_delegating_agent(
    orq=None,
    name: str = "refund-agent-delegating",
    advisor_model: str = "openai/gpt-5.6-sol",
    sidekick_model: str = "openai/gpt-5.4-nano",
) -> str:
    """A copy of the fixed agent with the two delegation tools (the advisor-and-sidekick module). Returns the agent key.

    Idempotency key: the agent `key`. Also ensures the knowledge base and the tools it needs.
    advisor: consults a stronger model mid-turn, the decision stays with the agent.
    sidekick: hands a self-contained writing task to a cheaper model, returns the artifact verbatim.
    """
    orq = orq or make_orq()
    key = K(name)
    try:
        orq.agents.retrieve(agent_key=key)
        return key
    except Exception:  # noqa: BLE001
        pass  # not found: create it below
    knowledge_base_id = ensure_knowledge_base(orq)
    payload = agent_payload("fixed", knowledge_base_id=knowledge_base_id, tool_keys=ensure_code_tools(orq))
    payload["key"] = key
    payload["display_name"] = "Refund agent (advisor + sidekick)"
    payload["instructions"] += (
        "\n\nDelegation:\n"
        "- Before refusing a post-window or above-limit request, ask the advisor whether the refusal is consistent with the policy text you fetched. "
        "Weigh the advice; the decision stays yours.\n"
        "- After any refund decision, delegate writing the two-sentence customer-facing closing note to the sidekick, giving it the decision and the order id. "
        "Return the sidekick's text verbatim as the last paragraph."
    )
    payload["settings"]["tool_approval_required"] = "none"
    payload["settings"]["tools"] += [
        {
            "type": "advisor",
            "configuration": {
                "model": advisor_model,
                "max_uses": 2,
                "max_transcript_tokens": 4000,
                "max_tokens": 400,
            },
        },
        {
            "type": "sidekick",
            "configuration": {
                "model": sidekick_model,
                "max_uses": 2,
                "max_tokens": 200,
                "system_prompt": "Write short, warm customer-service closing notes for Lumen Goods. Plain text, no markdown, no internal tool or policy names.",
                "output_format": "Two sentences.",
            },
        },
    ]
    orq.agents.create(**payload)
    return key


# ---------------------------------------------------------------- observability (the alerts-and-webhooks module)


def ensure_notifier(orq=None, name: str = "alert-notifier", url: str | None = None) -> str:
    """A generic webhook notifier. Alerts POST trigger-open and trigger-resolve events to it. Returns its id.

    Idempotency key: `display_name`. An existing notifier is re-pointed when the URL changed.
    """
    orq = orq or make_orq()
    key = K(name)
    url = url or settings.webhook_url
    for notifier in orq.notifiers.list(limit=100).data or []:
        if notifier.display_name == key:
            notifier_id = notifier.model_dump(by_alias=True)["_id"]
            if notifier.webhook_url != url:  # WS_WEBHOOK_URL changed (a new tunnel): re-point, do not recreate
                orq.notifiers.update(notifier_id=notifier_id, webhook_url=url)
            return notifier_id
    response = orq.notifiers.create(
        request={
            "type": "NOTIFIER_TYPE_WEBHOOK",
            "display_name": key,
            "webhook_url": url,
            "project_id": project_id(orq),
        }
    )
    return response.model_dump(by_alias=True)["notifier"]["_id"]


ALERT_THRESHOLD_USD = 0.002  # a burst of ten refund turns costs about twice this


def ensure_alert(orq=None, name: str = "cost-alert", notifier_id: str | None = None) -> str:
    """Spend above ALERT_THRESHOLD_USD in the last 5 minutes, checked every 5 minutes (the fastest the plan allows).

    Idempotency key: `display_name`, looked up over REST (see `list_alerts`). Returns the alert id.
    Cost, not error rate: alerts are project-scoped and failed requests are not attributed to a project,
    so an error-rate alert never sees the errors a workshop can cause. Cost is attributed on every agent call.
    """
    orq = orq or make_orq()
    key = K(name)
    for alert in list_alerts():
        if alert["display_name"] == key:
            return alert["alert_id"]
    created = orq.alerts.create(
        display_name=key,
        description=f"Workshop: LLM cost above ${ALERT_THRESHOLD_USD} in the last 5 minutes",
        project_id=project_id(orq),
        signal="cost",
        query={"metric": "genai.cost", "filters": []},
        condition={
            "comparator": "gt",
            "threshold": ALERT_THRESHOLD_USD,
            "window": "5m",
            "interval": "5m",
        },
        notifier_ids=[notifier_id] if notifier_id else None,
    )
    return created.model_dump(by_alias=True)["alert"]["alert_id"]


def ensure_annotation_queue(orq=None, name: str = "review-queue") -> str:
    """The queue the trace automation in the annotation-queues module fills; the alerts-and-webhooks module only points at it. Returns its id.

    Idempotency key: `display_name`.
    """
    orq = orq or make_orq()
    key = K(name)
    for queue in orq.annotation_queues.list(limit=100).data or []:
        if queue.display_name == key:
            return queue.model_dump(by_alias=True)["_id"]
    queue = orq.annotation_queues.create(
        display_name=key,
        description="Workshop: error traces to review (filled by the trace automation)",
        project_id=project_id(orq),
    )
    return queue.model_dump(by_alias=True)["_id"]


def ensure_webhook(
    orq=None,
    name: str = "events-webhook",
    url: str | None = None,
    events: tuple[str, ...] = ("llm.response", "agent.updated"),
) -> str:
    """A workspace webhook that delivers the given events to WS_WEBHOOK_URL, signed with WS_WEBHOOK_SECRET.

    Idempotency key: `display_name` (also passed as the webhook `id` on create). Returns its id.
    The secret is shared with the receiver, so it has to be in `.env` before the webhook exists;
    without one, a fresh secret is generated and printed, and the receiver cannot verify signatures.
    """
    orq = orq or make_orq()
    key = K(name)
    url = url or settings.webhook_url
    for webhook in orq.webhooks.list(limit=100).items or []:
        if webhook.display_name == key:
            webhook_id = webhook.model_dump(by_alias=True)["_id"]
            # Re-point (a new tunnel is a new URL) and re-enable: orq switches a webhook off after 10 failed
            # deliveries (`enabled: false`, `failure_count: 10`), which a dead tunnel reaches in minutes.
            # ponytail: REST; SDK 4.14 `webhooks.update` sends an empty body and `get` hides `enabled`.
            patch = {"url": url, "enabled": True}
            if settings.webhook_secret:  # the secret cannot be read back: push .env's on every run so signatures verify
                patch["secret"] = settings.webhook_secret
            rules_api("PATCH", f"/v2/webhooks/{webhook_id}", patch)
            return webhook_id
    secret = settings.webhook_secret or orq.webhooks.generate_secret().secret
    if not settings.webhook_secret:
        print("warning  : WS_WEBHOOK_SECRET is empty, using a generated secret")
        print("fix      : put the line below in .env and restart the receiver, or signatures will not verify")
        print(f"secret   : WS_WEBHOOK_SECRET={secret}")
    webhook = orq.webhooks.create(
        id=key,
        url=url,
        content_type="application/json",
        display_name=key,
        events=list(events),
        secret=secret,
    )
    return webhook.model_dump(by_alias=True)["_id"]


def list_alerts() -> list[dict[str, Any]]:
    """ponytail: REST. Once an alert has evaluated, its `recent_runs[].severity` is "" and the SDK's literal rejects it (4.17)."""
    return rest_get("/v2/alerts?limit=100")


def alert_triggers(alert_id: str) -> list[dict[str, Any]]:
    """Trigger history, newest first. REST for the same reason as `list_alerts`."""
    return rest_get(f"/v2/alerts/{alert_id}/triggers?limit=50")


def telemetry_query(orq, **body: Any) -> dict[str, Any]:
    """POST /v3/telemetry/query on the traces source. ponytail: REST, not orq.telemetry.query: SDK 4.17 rejects the echoed request (`sort: ""`)."""
    return rest_post(orq, "/v3/telemetry/query", {"source": "TELEMETRY_SOURCE_TRACES", **body})


# ---------------------------------------------------------------- reset


def rest_get(path: str) -> list[dict[str, Any]]:
    """Raw GET for lists where the SDK drops the `_id` field (MCP servers and gateways in 4.17)."""
    import httpx

    response = httpx.get(
        f"{settings.base_url}{path}",
        headers={"Authorization": f"Bearer {settings.bearer()}"},
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body  # most lists wrap rows in "data"


def project_id(orq=None) -> str | None:
    """The id of the workshop project (ORQ_PROJECT, matched on key or name), or None if it is missing."""
    orq = orq or make_orq()
    for project in orq.projects.list(limit=100).data or []:
        if project.key == settings.project or project.name == settings.project:
            return project.project_id
    return None


def rules_api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Routing rules and guardrail rules (`/v2/routing-rules`, `/v2/guardrail-rules`).

    Since orq API 4.14.17 these endpoints answer 403 `not authorized for this endpoint` to the
    repo's workspace key (a legacy `workspace_jwt` service-account token; two freshly minted keys of
    the same kind got the same 403), while `orq request` run from the instructor's shell works. So:
    try the key, and on 403 replay the call through the CLI with the shell's own ORQ_API_KEY, the
    one `.env` overrode at import time.
    """
    import os
    import shutil
    import subprocess

    import httpx

    response = httpx.request(
        method,
        f"{settings.base_url}{path}",
        json=body,
        headers={"Authorization": f"Bearer {settings.bearer()}"},
        timeout=60,
    )
    if response.status_code != 403:
        if response.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else {}

    # 403 for the key: replay through the `orq` CLI with the shell credential.
    if not shutil.which("orq"):
        raise RuntimeError(
            f"{method} {path} -> 403 for the API key and no `orq` CLI to fall back to; install it and `orq auth login`"
        )
    cmd = ["orq", "request", method, path, "--force", "--no-input", "-o", "json"] + (
        ["--stdin"] if body is not None else []
    )
    # .env values, not for the CLI
    env = {name: value for name, value in os.environ.items() if name not in ("ORQ_API_KEY", "ORQ_PROJECT")}
    if settings.shell_api_key:
        env["ORQ_API_KEY"] = settings.shell_api_key
    # stdin must be closed when there is no body: the CLI otherwise waits on a non-TTY stdin
    completed = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else "",
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    out = json.loads(completed.stdout) if completed.stdout.strip() else {}
    if completed.returncode or not (isinstance(out, dict) and out.get("ok", True)):
        if isinstance(out, dict):
            status = out.get("status")
            detail = json.dumps(out.get("body"))
        else:
            status = completed.returncode
            detail = completed.stderr
        raise RuntimeError(
            f"{method} {path}: 403 for the API key, and `orq request` with the shell credential answered "
            f"{status}: {detail[:200]}"
        )
    return (out.get("body") if isinstance(out, dict) else None) or {}


def _rules(path: str, orq) -> list[dict[str, Any]]:
    """Workspace-wide rules plus the ones scoped to the workshop project."""
    workshop_project_id = project_id(orq)
    rules = list(rules_api("GET", f"{path}?limit=100").get("data") or [])
    if workshop_project_id:
        rules += rules_api("GET", f"{path}?limit=100&project_id={workshop_project_id}").get("data") or []
    return rules


def _all_agents(orq) -> list[Any]:
    """Every page of agents.list: the workspace holds more than one page and the ws- ones sit at the end."""
    agents, after = [], None
    while True:
        page = orq.agents.list(limit=100, starting_after=after).data or []
        agents += page
        if len(page) < 100:  # a short page is the last one
            return agents
        last = page[-1].model_dump(by_alias=True)
        after = last.get("_id") or last.get("id")


def _dict_key(item) -> str:
    """The key of a raw REST row; rows without a key have a display_name instead."""
    return item.get("key") or item.get("display_name") or ""


def _dict_id(item) -> str:
    """The id of a raw REST row, whichever of `_id` / `id` the endpoint uses."""
    return item.get("_id") or item.get("id") or ""


def reset(orq=None) -> None:
    """Delete every entity whose key starts with `<prefix>-` or `<prefix>_`, kind by kind.

    Kinds run in the order listed: rules and agents first, then the entities they can point at
    (tools, knowledge bases, evaluators). Each kind is (label, list, delete, key of a row, id of
    a row). A kind that cannot be listed is skipped and a failed delete is reported; neither stops
    the run.
    """
    if settings.prefix == "ws" and "--yes" not in sys.argv:
        # The bare default is shared by everyone who never set a seat prefix: refuse to wipe it by accident.
        sys.exit("reset refused: WS_PREFIX is the shared default `ws`. Set your own seat prefix in .env (e.g. WS_PREFIX=ws07), or pass --yes.")
    orq = orq or make_orq()
    prefix = settings.prefix + "-"
    prefix_us = settings.prefix + "_"  # memory store keys reject hyphens
    removed = 0
    print("── Reset · delete every workshop entity ───────────────")
    print(f"prefix   : {prefix}, {prefix_us}")
    for kind, list_items, delete_item, key_of, id_of in [
        (
            "guardrail rule",
            lambda: _rules("/v2/guardrail-rules", orq),
            lambda i: rules_api("DELETE", f"/v2/guardrail-rules/{i}"),
            _dict_key,
            _dict_id,
        ),
        (
            "routing rule",
            lambda: _rules("/v2/routing-rules", orq),
            lambda i: rules_api("DELETE", f"/v2/routing-rules/{i}"),
            _dict_key,
            _dict_id,
        ),
        (
            "agent",
            lambda: _all_agents(orq),
            lambda i: rules_api("DELETE", f"/v2/agents/{i}"),  # REST: the SDK delete raises on its own 2xx body
            lambda x: x.key,
            lambda x: x.key,
        ),
        (
            "mcp gateway",
            lambda: rest_get("/v2/mcp-gateways?limit=100"),
            lambda i: orq.mcp_gateways.delete(id=i),
            _dict_key,
            _dict_id,
        ),
        (
            "mcp server",
            lambda: rest_get("/v2/mcp-servers?limit=100"),
            lambda i: orq.mcp_servers.delete(id=i),
            _dict_key,
            _dict_id,
        ),
        (
            "tool",
            lambda: orq.tools.list(limit=100).data,
            lambda i: orq.tools.delete(tool_id=i),
            lambda x: getattr(x, "key", ""),
            lambda x: x.id,
        ),
        (
            "knowledge base",
            lambda: orq.knowledge.list(limit=100).data,
            lambda i: orq.knowledge.delete(knowledge_id=i),
            lambda x: x.key,
            lambda x: x.id,
        ),
        (
            "memory store",
            lambda: orq.memory_stores.list(limit=100).data,
            lambda i: orq.memory_stores.delete(memory_store_key=i),
            lambda x: x.key,
            lambda x: x.key,
        ),
        (
            "evaluator",
            lambda: orq.evals.all(limit=100, search=settings.prefix + "-").data,
            lambda i: orq.evals.delete(id=i),
            lambda x: getattr(x, "key", ""),
            lambda x: getattr(x, "id", None) or x.model_dump().get("_id"),
        ),
        (
            "dataset",
            lambda: orq.datasets.list(limit=100, search=settings.prefix + "-").data,
            lambda i: orq.datasets.delete(dataset_id=i),
            lambda x: x.display_name,
            lambda x: x.id,
        ),
        (
            "smart router",
            lambda: orq.smart_routers.list(limit=100).data,
            lambda i: orq.smart_routers.delete(smart_router_id=i),
            lambda x: x.key,
            lambda x: x.smart_router_id,
        ),
        (
            "alert",
            list_alerts,
            lambda i: orq.alerts.delete(alert_id=i),
            lambda x: x["display_name"],
            lambda x: x["alert_id"],
        ),
        (
            "notifier",
            lambda: orq.notifiers.list(limit=100).data,
            lambda i: orq.notifiers.delete(notifier_id=i),
            lambda x: x.display_name,
            lambda x: x.model_dump(by_alias=True)["_id"],
        ),
        (
            "annotation queue",
            lambda: orq.annotation_queues.list(limit=100).data,
            lambda i: orq.annotation_queues.delete(annotation_queue_id=i),
            lambda x: x.display_name,
            lambda x: x.model_dump(by_alias=True)["_id"],
        ),
        (
            "webhook",
            lambda: orq.webhooks.list(limit=100).items,
            lambda i: orq.webhooks.delete(id=i),
            lambda x: x.display_name,
            lambda x: x.model_dump(by_alias=True)["_id"],
        ),
    ]:
        try:
            items = list_items() or []
        except Exception as exc:
            print(f"skipped  : {kind} ({type(exc).__name__})")
            continue
        for item in items:
            if (key_of(item) or "").startswith((prefix, prefix_us)):
                try:
                    delete_item(id_of(item))
                    print(f"deleted  : {kind} {key_of(item)}")
                    removed += 1
                except Exception as exc:
                    print(f"failed   : {kind} {key_of(item)}: {str(exc)[:120]}")
    print(f"removed  : {removed} entities")
    print("next     : run `make seed-workspace` or a module to create them again")


def seed(orq=None) -> None:
    """Create every entity the modules expect, for a learner who joins late. Safe to rerun.

    Prints one id or key per entity as it goes, so a failure shows which one broke.
    """
    orq = orq or make_orq()
    started = time.time()
    print("── Seed · create every workshop entity ────────────────")
    print(f"dataset  : {ensure_dataset(orq)} ({K('refund-eval')})")
    print(f"kb       : {ensure_knowledge_base(orq)} ({K('refund-policy')})")
    print(f"guard    : {ensure_python_guardrail(orq)} ({K('refund-limit-guard')})")
    for choice in CHAT_CHANNELS:
        try:
            print(f"chat rule: {ensure_chat_guardrail_rule(orq, choice)} ({choice}, the chat's Guardrails dropdown)")
        except RuntimeError as exc:  # rules need an admin key: the rest of the seed must not stop here
            print(f"chat rule: skipped {choice}: {str(exc)[:100]}")
    print(f"judge    : {ensure_llm_judge(orq)} ({K('refund-policy-judge')})")
    knowledge_base_id = ensure_knowledge_base(orq)  # already exists: returns the id without work
    tool_keys = ensure_code_tools(orq)
    print(f"tools    : {', '.join(tool_keys)} (code tools: orq runs them)")
    print(f"agent    : {ensure_agent(orq, 'fixed', knowledge_base_id=knowledge_base_id, tool_keys=tool_keys)}")
    print(f"agent    : {ensure_agent(orq, 'vulnerable', knowledge_base_id=knowledge_base_id, tool_keys=tool_keys)}")
    print(f"agent    : {ensure_delegating_agent(orq)}")
    function_keys = ensure_tools(orq)
    print(f"tools    : {', '.join(function_keys)} (function tools: your code runs them)")
    print(f"agent    : {ensure_agent(orq, 'fixed', tool_keys=function_keys, tool_kind='function')}")
    notifier_id = ensure_notifier(orq)
    print(f"notifier : {notifier_id} ({K('alert-notifier')})")
    print(f"alert    : {ensure_alert(orq, notifier_id=notifier_id)} ({K('cost-alert')})")
    print(f"queue    : {ensure_annotation_queue(orq)} ({K('review-queue')})")
    print(f"dataset  : {ensure_dataset(orq, 'review-dataset', rows=None)} ({K('review-dataset')}, empty)")
    print(f"elapsed  : {time.time() - started:.0f}s")
    print(f"next     : every entity sits under {settings.path} in the Studio ({settings.base_url})")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "seed"
    {"seed": seed, "reset": reset}[command]()
