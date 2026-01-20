"""
OpenTelemetry tracing initialization for HTBase services.

Provides distributed tracing with proper context propagation
across FastAPI and Celery services.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def init_tracing_fastapi(
    service_name: str,
    otel_endpoint: Optional[str],
    version: str = "unknown",
    environment: str = "development",
) -> bool:
    """Initialize OpenTelemetry tracing for FastAPI applications.

    Args:
        service_name: Service name for traces
        otel_endpoint: OTLP endpoint URL (None to skip initialization)
        version: Application version
        environment: Environment name

    Returns:
        True if tracing was initialized, False otherwise
    """
    if not otel_endpoint:
        logger.info("OTEL endpoint not configured, skipping tracing initialization")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Create resource with service metadata
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: version,
            "deployment.environment": environment,
        })

        # Create and set tracer provider
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        # Instrument FastAPI (will auto-instrument when app is created)
        FastAPIInstrumentor.instrument()

        logger.info(
            f"OpenTelemetry tracing initialized for {service_name}",
            extra={
                "otel_endpoint": otel_endpoint,
                "version": version,
                "environment": environment,
            },
        )
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry tracing: {e}")
        return False


def init_tracing_celery(
    service_name: str,
    otel_endpoint: Optional[str],
    version: str = "unknown",
    environment: str = "development",
) -> bool:
    """Initialize OpenTelemetry tracing for Celery workers.

    Args:
        service_name: Service name for traces
        otel_endpoint: OTLP endpoint URL (None to skip initialization)
        version: Application version
        environment: Environment name

    Returns:
        True if tracing was initialized, False otherwise
    """
    if not otel_endpoint:
        logger.info("OTEL endpoint not configured, skipping tracing initialization")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        # Create resource with service metadata
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: version,
            "deployment.environment": environment,
        })

        # Create and set tracer provider
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        # Instrument Celery
        CeleryInstrumentor().instrument()

        logger.info(
            f"OpenTelemetry tracing initialized for {service_name}",
            extra={
                "otel_endpoint": otel_endpoint,
                "version": version,
                "environment": environment,
            },
        )
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry tracing: {e}")
        return False


def get_tracer(name: str):
    """Get a tracer instance for manual instrumentation.

    Args:
        name: Tracer name (usually module name)

    Returns:
        Tracer instance (or no-op tracer if not initialized)
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        # Return a no-op tracer if OTEL not available
        class NoOpTracer:
            def start_span(self, name, **kwargs):
                return NoOpSpan()

            def start_as_current_span(self, name, **kwargs):
                return NoOpSpan()

        class NoOpSpan:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def set_attribute(self, key, value):
                pass

            def add_event(self, name, attributes=None):
                pass

            def set_status(self, status):
                pass

        return NoOpTracer()
