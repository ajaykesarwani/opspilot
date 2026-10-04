import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from prometheus_client import Counter, Histogram, Gauge

# Metrics
# Use global singletons for Prometheus metrics
request_count = Counter("opspilot_request_count", "Total number of requests", ["endpoint", "status"])
workflow_success = Counter("opspilot_workflow_success", "Successful workflows")
workflow_failure = Counter("opspilot_workflow_failure", "Failed workflows", ["reason"])
workflow_duration = Histogram("opspilot_workflow_duration_seconds", "Workflow duration in seconds")
retrieval_duration = Histogram("opspilot_retrieval_duration_seconds", "Retrieval duration in seconds")
provider_failures = Counter("opspilot_provider_failures", "LLM Provider failures")

def setup_telemetry(service_name: str):
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    
    # Configure exporters based on environment
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    else:
        # Default to console exporter in local dev mode
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
def get_tracer(module_name: str):
    return trace.get_tracer(module_name)
