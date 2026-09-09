"""Clients. Two doors into orq: OpenAI-compatible router, and the native SDK."""

from __future__ import annotations

from openai import OpenAI
from orq_ai_sdk import Orq

from .config import settings


def make_openai_client() -> OpenAI:
    """OpenAI SDK pointed at the orq AI Gateway. Any OpenAI-compatible framework works the same way."""
    settings.require_key()
    return OpenAI(api_key=settings.api_key, base_url=settings.router_url)


def make_orq() -> Orq:
    """Native orq SDK: agents, knowledge, evals, datasets, traces, budgets, MCP."""
    settings.require_key()
    return Orq(api_key=settings.api_key, server_url=settings.base_url)
