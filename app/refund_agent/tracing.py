"""Optional OpenTelemetry setup. Module 02 turns it on with TRACING=otel.

The gateway already traces every model call with zero code. This file adds our own spans
around the agent loop and each tool, so one trace reads agent -> tool -> llm instead of
one trace per model call. The gateway spans nest under ours because `agent.py` forwards
the `traceparent` header on every request.

    from app.refund_agent import tracing
    tracing.setup_otel()   # once, before the first call
    ...
    tracing.flush()        # last, or a short script exits before the batch ships
"""

from __future__ import annotations

from .config import settings

_provider = None  # the TracerProvider once setup_otel has run; None means "not exporting"


def setup_otel(service_name: str = "refund-agent", force: bool = False) -> bool:
    """Export spans to orq over OTLP/HTTP. Returns False when TRACING != otel (unless force).

    Safe to call more than once: the second call is a no-op that returns True. The OpenTelemetry
    imports live inside the function so `app/` imports cleanly when the packages are absent.
    """
    global _provider
    if _provider is not None:
        return True
    if settings.tracing != "otel" and not force:
        return False
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_url}/v1/traces",
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    _provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(_provider)
    return True


def flush() -> None:
    """Ship what the batch exporter still holds. Short scripts exit before it would on its own."""
    if _provider is not None:
        _provider.force_flush()
