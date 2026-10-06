"""OpenTelemetry tracing setup and Prometheus metrics (process-wide singletons)."""

import logging
import os
import threading

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

request_count = Counter("opspilot_request_count", "Requests handled", ["endpoint", "status"])
workflow_success = Counter("opspilot_workflow_success", "Workflows reaching human review")
workflow_failure = Counter("opspilot_workflow_failure", "Failed workflows", ["reason"])
workflow_duration = Histogram("opspilot_workflow_duration_seconds", "Workflow duration")
retrieval_duration = Histogram("opspilot_retrieval_duration_seconds", "Retrieval duration")
provider_failures = Counter("opspilot_provider_failures", "LLM provider failures")
dlq_messages = Counter("opspilot_dlq_messages", "Messages dead-lettered", ["reason"])

_lock = threading.Lock()
_configured = False


def setup_telemetry(service_name: str) -> None:
    """Configure tracing once per process. Safe to call repeatedly (e.g. per test app).

    Exporter selection: OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set; console when
    OTEL_TRACES_EXPORTER=console; otherwise spans are created but not exported.
    """
    global _configured
    with _lock:
        if _configured:
            return
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
            )
        elif os.environ.get("OTEL_TRACES_EXPORTER") == "console":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _configured = True


def get_tracer(module_name: str) -> trace.Tracer:
    return trace.get_tracer(module_name)
