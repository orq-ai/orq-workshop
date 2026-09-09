"""Optional OpenTelemetry setup. Module 02 turns it on with TRACING=otel.

Gateway calls are traced with zero code. This adds our own spans around the
agent loop and each tool so a trace reads: agent -> tool -> llm.
"""

from __future__ import annotations

from .config import settings

_provider = None


def setup_otel(service_name: str = "refund-agent", force: bool = False) -> bool:
    """Export spans to orq over OTLP/HTTP. Returns False when TRACING != otel (unless force)."""
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
    """Short scripts exit before the batch exporter ships. Call this last."""
    if _provider is not None:
        _provider.force_flush()
