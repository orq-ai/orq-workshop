"""The insurance claims demo: the cookbook's agents, evaluators and test cases, seeded from this repo.

What: `seed()` creates what the "insurance claims MCP cookbook" builds, with the workshop prefix
(`ws-claims-assessor`, ...), from the files in `app/data/insurance/`: 2 scoring evaluators, 6
guardrail or format evaluators, 5 agents (one single agent, an orchestrator and its three
sub-agents) and the 15-case dataset. Safe to rerun: each entity is looked up by key first.

    uv run python -m app.insurance        # or: make seed-insurance

The chat's Insurance demo (`app/web.py`) chats with these agents. Their instructions are Dutch
and follow Dutch motor insurance rules (WA, WA+, Allrisk; own risk EUR 150 or 300; total loss at
75% of the car's value; 10% depreciation from five years).
"""

from __future__ import annotations

import json
from typing import Any

from .refund_agent.client import make_orq
from .refund_agent.config import DATA_DIR, settings
from .refund_agent.entities import K, _find_eval, ensure_dataset, rest_post, rules_api

DIR = DATA_DIR / "insurance"
DATASET = "insurance-claims-test-cases"  # K(...) -> ws-insurance-claims-test-cases
EVALUATOR_FIELDS = ("type", "description", "output_type", "guardrail_config", "code", "prompt", "model", "mode")
# The chat's Guardrails dropdown in this demo: choice -> [(evaluator key without prefix, execute_on)].
GUARD_CHOICES: dict[str, list[tuple[str, str]]] = {
    "input": [("claims-input-guard", "input")],
    "output": [("claims-output-guard", "output")],
    "legal": [("claims-no-legal-advice", "output")],
    "payout": [("claims-payout-limit", "output")],
    "all": [
        ("claims-input-guard", "input"),
        ("claims-output-guard", "output"),
        ("claims-no-legal-advice", "output"),
        ("claims-payout-limit", "output"),
    ],
}
# metadata.channel the chat sends for each choice; one gateway rule per choice matches it.
CHANNELS = {choice: K(f"chat-ins-{choice}") for choice in GUARD_CHOICES}


def load(name: str) -> Any:
    return json.loads((DIR / name).read_text())


def agent_keys() -> list[str]:
    """Prefixed keys of the five claims agents, the single agent first."""
    return [K(a["key"]) for a in load("agents.json")]


def ensure_evaluators(orq=None) -> dict[str, str]:
    """Create each evaluator of `evaluators.json`. Returns {unprefixed key: id}.

    Idempotency key: the evaluator `key`. REST, like the refund guardrail: the SDK cannot
    serialize the python_eval union in 4.14.x.
    """
    orq = orq or make_orq()
    ids: dict[str, str] = {}
    for spec in load("evaluators.json"):
        key = K(spec["key"])
        found = _find_eval(orq, key)
        if not found:
            body = {"key": key, **{f: spec[f] for f in EVALUATOR_FIELDS if f in spec}}
            created = rest_post(orq, "/v2/evaluators", body)
            found = created.get("id") or created.get("_id") or _find_eval(orq, key)
        ids[spec["key"]] = found
    return ids


def _agent_body(spec: dict[str, Any], evaluator_ids: dict[str, str]) -> dict[str, Any]:
    """The `agents.create` body: keys prefixed, evaluator keys turned into ids, tools reduced to their type."""
    settings_ = dict(spec["settings"])
    for field in ("evaluators", "guardrails"):
        if field in settings_:
            settings_[field] = [
                {"id": evaluator_ids[i["key"]], "execute_on": i["execute_on"], "sample_rate": i.get("sample_rate", 100)}
                for i in settings_[field]
            ]
    settings_["tools"] = [{"type": t["action_type"]} for t in settings_.get("tools", [])]
    body: dict[str, Any] = {
        "key": K(spec["key"]),
        "display_name": spec["display_name"],
        "role": spec["role"],
        "description": spec["description"],
        "instructions": spec["instructions"],
        "model": spec["model"],
        "settings": settings_,
        "path": getattr(settings, "path", None) or f"{settings.project}/workshop",  # the SDK requires it
    }
    if spec.get("team_of_agents"):
        body["team_of_agents"] = [{"key": K(t["key"])} for t in spec["team_of_agents"]]
    return body


def ensure_agents(orq=None, evaluator_ids: dict[str, str] | None = None) -> list[str]:
    """Create the five agents, sub-agents before the orchestrator. Returns their prefixed keys.

    Idempotency key: the agent `key`. An existing agent is left as is.
    """
    orq = orq or make_orq()
    evaluator_ids = evaluator_ids or ensure_evaluators(orq)
    specs = sorted(load("agents.json"), key=lambda s: bool(s.get("team_of_agents")))  # leaves first
    for spec in specs:
        body = _agent_body(spec, evaluator_ids)
        try:
            orq.agents.retrieve(agent_key=body["key"])
            exists = True
        except Exception:  # noqa: BLE001  not found (or not readable): create it below
            exists = False
        if not exists:
            orq.agents.create(**body)
    return agent_keys()


def ensure_chat_rules(orq=None, evaluator_ids: dict[str, str] | None = None) -> dict[str, str]:
    """One workspace-wide gateway rule per Guardrails choice, matched on `metadata.channel`.

    Same idea as the refund demo's rules (`entities.ensure_chat_guardrail_rule`): request-level
    `guardrails` are ignored on `/v3/router/responses`, rules are not. Rules need an admin key.
    Idempotency key: the rule's display name. Returns {choice: rule id}.
    """
    orq = orq or make_orq()
    evaluator_ids = evaluator_ids or ensure_evaluators(orq)
    existing = {r["display_name"]: r for r in rules_api("GET", "/v2/guardrail-rules?limit=100").get("data") or []}
    rule_ids: dict[str, str] = {}
    for choice, guards in GUARD_CHOICES.items():
        name = K(f"guardrail-rule-chat-ins-{choice}")
        if name in existing:
            rule = existing[name]
        else:
            body = {
                "display_name": name,
                "description": f"Insurance chat Guardrails dropdown ({choice}): calls tagged channel={CHANNELS[choice]}",
                "enabled": True,
                "expression": {"cel": f'metadata["channel"] == "{CHANNELS[choice]}"'},
                "guardrails": [{"id": evaluator_ids[key], "execute_on": stage} for key, stage in guards],
            }
            created = rules_api("POST", "/v2/guardrail-rules", body)
            rule = created.get("guardrail_rule", created)
        rule_ids[choice] = rule.get("_id") or rule.get("id")
    return rule_ids


def prompts() -> list[dict[str, str]]:
    """The example prompts of the chat's Insurance demo: {group, label, text}."""
    return load("prompts.json")


def test_cases() -> list[dict[str, str]]:
    """The 15 test cases: {input, expected} in dataset order (5 covered, 5 not covered, 3 edge, 2 incomplete)."""
    rows = [json.loads(line) for line in (DIR / "testcases.jsonl").read_text().splitlines() if line.strip()]
    return [{"input": r["inputs"]["user_input"], "expected": r["expected_output"]} for r in rows]


def rules() -> list[str]:
    """The Dutch motor-insurance rules the agents work from: the bullet lines of the assessor's instructions."""
    text = next(a["instructions"] for a in load("agents.json") if a["key"] == "claims-assessor")
    block = text.split("Regels", 1)[1].split("Antwoord altijd", 1)[0]
    return [line[2:] for line in block.splitlines() if line.startswith("- ")]


def seed(orq=None) -> None:
    """Evaluators, dataset, agents. Prints one line per entity so a failure shows which one broke."""
    orq = orq or make_orq()
    print("── Seed · insurance claims demo ───────────────────────")
    ids = ensure_evaluators(orq)
    for key, evaluator_id in ids.items():
        print(f"evaluator: {evaluator_id} ({K(key)})")
    print(f"dataset  : {ensure_dataset(orq, DATASET, rows=DIR / 'testcases.jsonl')} ({K(DATASET)}, 15 cases)")
    for key in ensure_agents(orq, ids):
        print(f"agent    : {key}")
    try:
        for choice, rule_id in ensure_chat_rules(orq, ids).items():
            print(f"chat rule: {rule_id} ({choice}, the chat's Guardrails dropdown)")
    except RuntimeError as exc:  # rules need an admin key: the rest of the seed must not stop here
        print(f"chat rule: skipped: {str(exc)[:100]}")
    print(f"next     : `make chat`, Demo: Insurance ({settings.base_url})")


if __name__ == "__main__":
    seed()
