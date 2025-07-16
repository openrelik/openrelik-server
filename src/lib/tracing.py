import os

from opentelemetry import trace

from opentelemetry.exporter.otlp.proto.grpc import trace_exporter as grpc_exporter
from opentelemetry.exporter.otlp.proto.http import trace_exporter as http_exporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_telemetry(service_name: str):
    """Configures the OpenTelemetry trace exporter.

    Args:
        service_name (str): the service name used to identify generated traces.
    """

    resource = Resource(attributes={
        "service.name": service_name
    })

    # --- Tracing Setup ---
    trace.set_tracer_provider(TracerProvider(resource=resource))

    otel_mode = os.environ.get("OTEL_MODE", "otlp-grpc")
    otlp_grpc_endpoint = os.environ.get("OTLP_GRPC_ENDPOINT", "jaeger-collector:4317")
    otlp_http_endpoint = os.environ.get("OTLP_HTTP_ENDPOINT", "http://jaeger-collector:4318/v1/traces")

    trace_exporter = None
    if otel_mode == "otlp-grpc":
        trace_exporter = grpc_exporter.OTLPSpanExporter(
                endpoint=otlp_grpc_endpoint, insecure=True)
    elif otel_mode == "otlp-http":
        trace_exporter = http_exporter.OTLPSpanExporter(
                endpoint=otlp_http_endpoint)
    else:
        raise Exception("Unsupported OTEL tracing mode %s", otel_mode)

    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(trace_exporter))
