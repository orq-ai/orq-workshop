"""The two doors into orq: the OpenAI-compatible gateway and the native SDK.

Both use the same credential: ORQ_API_KEY, or the `orq auth login` session when it is empty.
The gateway is what the refund agent calls (module 01 onwards); the
native SDK is what the modules use to create and inspect entities (agents, knowledge,
evaluators, datasets, traces, budgets, MCP).
"""

from __future__ import annotations

from openai import OpenAI
from orq_ai_sdk import Orq

from .config import settings


def make_openai_client() -> OpenAI:
    """The OpenAI SDK pointed at the orq AI Gateway.

    Nothing orq-specific here: any OpenAI-compatible framework is wired the same way, base URL
    and key. That is the whole integration for LangGraph, Strands and friends.
    """
    return OpenAI(api_key=settings.bearer(), base_url=settings.router_url)


def make_orq() -> Orq:
    """The native orq SDK: agents, knowledge, evals, datasets, traces, budgets, MCP."""
    return Orq(api_key=settings.bearer(), server_url=settings.base_url)
