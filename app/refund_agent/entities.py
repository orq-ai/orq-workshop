"""Idempotent create/delete of every orq entity the workshop uses.

Every key starts with WS_PREFIX so `reset` can find them. Modules call the
`ensure_*` helpers; `seed` creates everything at once for latecomers.

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


# ---------------------------------------------------------------- datasets

def ensure_dataset(orq=None, name: str = "refund-eval", rows: Path = DATA_DIR / "dataset.jsonl") -> str:
    orq = orq or make_orq()
    key = K(name)
    for d in orq.datasets.list(limit=100).data or []:
        if d.display_name == key:
            return d.id
    ds = orq.datasets.create(request={"display_name": key, "path": settings.path})
    points = [json.loads(l) for l in rows.read_text().splitlines() if l.strip()]
    orq.datasets.create_datapoint(dataset_id=ds.id, request_body=points)
    return ds.id


# ---------------------------------------------------------------- knowledge base

def ensure_knowledge_base(orq=None, name: str = "refund-policy", docs: Path = DATA_DIR / "kb") -> str:
    """Create the KB, one datasource per policy file, chunked with the Chunking API."""
    orq = orq or make_orq()
    key = K(name)
    for kb in orq.knowledge.list(limit=100).data or []:
        if kb.key == key:
            return kb.id
    kb = orq.knowledge.create(request={
        "key": key,
        "embedding_model": settings.embedding_model,
        "path": settings.path,
        "description": "Lumen Goods refund policy (workshop)",
    })
    for md in sorted(docs.glob("*.md")):
        ds = orq.knowledge.create_datasource(knowledge_id=kb.id, display_name=md.name)
        chunked = orq.chunking.parse(request={"text": md.read_text(), "strategy": "recursive", "chunk_size": 300, "chunk_overlap": 40})
        orq.knowledge.create_chunks(
            knowledge_id=kb.id,
            datasource_id=ds.id,
            request_body=[{"text": c.text, "metadata": {"topic": md.stem}} for c in chunked.chunks],
        )
    return kb.id


# ---------------------------------------------------------------- evaluators

def ensure_python_guardrail(orq=None, name: str = "refund-limit-guard") -> str:
    """Blocks any assistant output that promises a refund above the EUR 500 limit."""
    orq = orq or make_orq()
    key = K(name)
    existing = _find_eval(orq, key)
    if existing:
        return existing
    code = (Path(__file__).parent / "guardrail_refund_limit.py").read_text()
    # ponytail: REST, not orq.evals.create. The SDK's python_eval union lacks the `mode` discriminator (4.14.x).
    return rest_post(orq, "/v2/evaluators", {
        "type": "python_eval",
        "key": key,
        "description": "Fail when the output commits to refunding more than EUR 500.",
        "path": settings.path,
        "code": code,
        "output_type": "boolean",  # without it the evaluator is stored as number and every guardrail call 502s
        "guardrail_config": {"enabled": True, "type": "boolean", "value": True},
    })["id"]


def ensure_llm_judge(orq=None, name: str = "refund-policy-judge") -> str:
    """Binary judge: did the assistant follow the refund policy?"""
    orq = orq or make_orq()
    key = K(name)
    existing = _find_eval(orq, key)
    if existing:
        return existing
    prompt = (DATA_DIR / "judge_prompt.md").read_text()
    ev = orq.evals.create(request={
        "type": "llm_eval",
        "key": key,
        "description": "Pass when the refund decision matches policy, fail otherwise.",
        "path": settings.path,
        "prompt": prompt,
        "model": settings.judge_model,
        "mode": "single",
        "output_type": "boolean",
        "guardrail_config": {"enabled": False, "type": "boolean", "value": True},
    })
    return ev.id


def rest_post(orq, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Raw POST with the same credentials, for the few endpoints the SDK cannot serialize."""
    import httpx

    r = httpx.post(f"{settings.base_url}{path}", json=body, headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
    body = r.json()
    return body.get("document", body)  # some endpoints wrap the entity


def _find_eval(orq, key: str) -> str | None:
    for ev in orq.evals.all(limit=50, search=key).data or []:
        if getattr(ev, "key", None) == key:
            return getattr(ev, "id", None) or ev.model_dump().get("_id")
    return None


# ---------------------------------------------------------------- tools

def ensure_tools(orq=None) -> list[str]:
    """Register the three function tools as Tool entities. Agents reference them by key."""
    from .tools import TOOL_SCHEMAS

    orq = orq or make_orq()
    existing = {t.key for t in (orq.tools.list(limit=100).data or []) if getattr(t, "key", None)}
    keys = []
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        key = K(fn["name"].replace("_", "-"))
        keys.append(key)
        if key in existing:
            continue
        orq.tools.create(request={
            "type": "function",
            "key": key,
            "path": settings.path,
            "description": fn["description"],
            "function": {"name": fn["name"], "description": fn["description"], "parameters": fn["parameters"]},
        })
    return keys


# ---------------------------------------------------------------- agents

def agent_payload(variant: str = "fixed", knowledge_base_id: str | None = None, memory_store_id: str | None = None, tool_keys: list[str] | None = None) -> dict[str, Any]:
    instructions = (DATA_DIR / f"{variant}_instructions.md").read_text()
    tools: list[dict[str, Any]] = [{"type": "function", "key": k} for k in tool_keys or ensure_tools()]
    payload: dict[str, Any] = {
        "key": K(f"refund-agent-{variant}") if variant != "fixed" else K("refund-agent"),
        "display_name": f"Refund agent ({variant})",
        "role": "Customer-service refund agent for Lumen Goods.",
        "description": "Handles refund requests for authenticated retail customers. Tools: lookup_order, get_policy, issue_refund.",
        "instructions": instructions,
        "path": settings.path,
        "model": settings.model,
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
    orq = orq or make_orq()
    payload = agent_payload(variant, **kw)
    try:
        orq.agents.retrieve(agent_key=payload["key"])
        return payload["key"]
    except Exception:
        pass
    orq.agents.create(**payload)
    return payload["key"]


# ---------------------------------------------------------------- reset

def rest_get(path: str) -> list[dict[str, Any]]:
    """Raw GET for lists where the SDK drops the `_id` field (MCP servers and gateways in 4.14)."""
    import httpx

    r = httpx.get(f"{settings.base_url}{path}", headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=60)
    r.raise_for_status()
    body = r.json()
    return body.get("data", body) if isinstance(body, dict) else body


def project_id(orq=None) -> str | None:
    orq = orq or make_orq()
    for p in orq.projects.list(limit=100).data or []:
        if p.key == settings.project or p.name == settings.project:
            return p.project_id
    return None


def _rules(path: str, orq) -> list[dict[str, Any]]:
    """Workspace-wide rules plus the ones scoped to the workshop project."""
    pid = project_id(orq)
    out = rest_get(f"{path}?limit=100")
    if pid:
        out += rest_get(f"{path}?limit=100&project_id={pid}")
    return out


def _dict_key(x) -> str:
    return x.get("key") or x.get("display_name") or ""


def _dict_id(x) -> str:
    return x.get("_id") or x.get("id") or ""

def reset(orq=None) -> None:
    orq = orq or make_orq()
    prefix = settings.prefix + "-"
    prefix_us = settings.prefix + "_"  # memory store keys reject hyphens
    n = 0
    for name, lister, deleter, keyf, idf in [
        ("guardrail rule", lambda: _rules("/v2/guardrail-rules", orq), lambda i: orq.guardrail_rules.delete(guardrail_rule_id=i), _dict_key, _dict_id),
        ("routing rule", lambda: _rules("/v2/routing-rules", orq), lambda i: orq.routing_rules.delete(routing_rule_id=i), _dict_key, _dict_id),
        ("agent", lambda: orq.agents.list(limit=100).data, lambda i: orq.agents.delete(agent_key=i), lambda x: x.key, lambda x: x.key),
        ("mcp gateway", lambda: rest_get("/v2/mcp-gateways?limit=100"), lambda i: orq.mcp_gateways.delete(id=i), _dict_key, _dict_id),
        ("mcp server", lambda: rest_get("/v2/mcp-servers?limit=100"), lambda i: orq.mcp_servers.delete(id=i), _dict_key, _dict_id),
        ("tool", lambda: orq.tools.list(limit=100).data, lambda i: orq.tools.delete(tool_id=i), lambda x: getattr(x, "key", ""), lambda x: x.id),
        ("knowledge base", lambda: orq.knowledge.list(limit=100).data, lambda i: orq.knowledge.delete(knowledge_id=i), lambda x: x.key, lambda x: x.id),
        ("memory store", lambda: orq.memory_stores.list(limit=100).data, lambda i: orq.memory_stores.delete(memory_store_key=i), lambda x: x.key, lambda x: x.key),
        ("evaluator", lambda: orq.evals.all(limit=100).data, lambda i: orq.evals.delete(id=i), lambda x: getattr(x, "key", ""), lambda x: x.id),
        ("dataset", lambda: orq.datasets.list(limit=100).data, lambda i: orq.datasets.delete(dataset_id=i), lambda x: x.display_name, lambda x: x.id),
        ("smart router", lambda: orq.smart_routers.list(limit=100).data, lambda i: orq.smart_routers.delete(smart_router_id=i), lambda x: x.key, lambda x: x.smart_router_id),
    ]:
        try:
            items = lister() or []
        except Exception as exc:
            print(f"skip {name}: {type(exc).__name__}")
            continue
        for it in items:
            if (keyf(it) or "").startswith((prefix, prefix_us)):
                try:
                    deleter(idf(it))
                    print(f"deleted {name} {keyf(it)}")
                    n += 1
                except Exception as exc:
                    print(f"failed {name} {keyf(it)}: {str(exc)[:120]}")
    print(f"reset done, {n} entities removed")


def seed(orq=None) -> None:
    orq = orq or make_orq()
    t = time.time()
    print("dataset      ", ensure_dataset(orq))
    print("knowledge    ", ensure_knowledge_base(orq))
    print("guardrail    ", ensure_python_guardrail(orq))
    print("judge        ", ensure_llm_judge(orq))
    kb = ensure_knowledge_base(orq)
    tools = ensure_tools(orq)
    print("tools        ", tools)
    print("agent fixed  ", ensure_agent(orq, "fixed", knowledge_base_id=kb, tool_keys=tools))
    print("agent vuln   ", ensure_agent(orq, "vulnerable", knowledge_base_id=kb, tool_keys=tools))
    print(f"seed done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    {"seed": seed, "reset": reset}[cmd]()
