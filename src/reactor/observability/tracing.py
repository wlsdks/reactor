from __future__ import annotations

import os
import re
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode

from reactor.core.settings import Settings

REACTOR_TRACER_NAME = "reactor"
LANGSMITH_ENV_NAMES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_API_KEY",
    "LANGSMITH_HIDE_INPUTS",
    "LANGSMITH_HIDE_OUTPUTS",
    "LANGSMITH_HIDE_METADATA",
)
_configured_tracer_provider: TracerProvider | None = None

type SpanAttributeValue = str | bool | int | float
REDACTED = "[REDACTED]"
SENSITIVE_ATTRIBUTE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)
SECRET_SHAPED_ATTRIBUTE_VALUE_RE = re.compile(
    r"(?i)("
    r"\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*\S{8,}"
    r"|"
    r"\b(?:sk|rk|pk|xox[baprs]|gh[pousr]|github_pat)_[A-Za-z0-9_\-]{8,}"
    r"|"
    r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{12,}"
    r")"
)
EMAIL_ATTRIBUTE_VALUE_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


@dataclass(frozen=True)
class TracingConfigurationResult:
    enabled: bool
    exporter: str
    endpoint: str | None = None


def configure_tracing(settings: Settings) -> TracingConfigurationResult:
    global _configured_tracer_provider

    exporter_name = normalize_trace_exporter(settings.observability_trace_exporter)
    if not settings.observability_tracing_enabled or exporter_name == "none":
        clear_langsmith_environment()
        return TracingConfigurationResult(enabled=False, exporter="none")

    if exporter_name == "langsmith":
        langsmith_endpoint = configure_langsmith_environment(settings)
        return TracingConfigurationResult(
            enabled=True,
            exporter=exporter_name,
            endpoint=langsmith_endpoint,
        )

    clear_langsmith_environment()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.app_name,
                "deployment.environment": settings.environment,
            }
        ),
        sampler=TraceIdRatioBased(settings.observability_trace_sample_ratio),
    )
    trace_endpoint: str | None = None
    exporter: SpanExporter
    if exporter_name == "console":
        exporter = ConsoleSpanExporter()
    elif exporter_name == "otlp_http":
        trace_endpoint = optional_non_blank(settings.observability_otlp_endpoint)
        exporter = OTLPSpanExporter(
            endpoint=trace_endpoint,
            headers=parse_otlp_headers(settings.observability_otlp_headers),
        )
    else:
        raise ValueError(f"Unsupported trace exporter: {settings.observability_trace_exporter}")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured_tracer_provider = provider
    return TracingConfigurationResult(
        enabled=True,
        exporter=exporter_name,
        endpoint=trace_endpoint,
    )


def shutdown_tracing() -> None:
    global _configured_tracer_provider

    provider = _configured_tracer_provider
    _configured_tracer_provider = None
    if provider is None:
        return
    try:
        provider.force_flush()
    finally:
        provider.shutdown()


def normalize_trace_exporter(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"", "disabled", "off"}:
        return "none"
    if normalized in {"otlp", "otlphttp"}:
        return "otlp_http"
    if normalized in {"langsmith_tracing", "smith"}:
        return "langsmith"
    return normalized


def configure_langsmith_environment(settings: Settings) -> str | None:
    os.environ["LANGSMITH_TRACING"] = "true"
    set_or_clear_env("LANGSMITH_PROJECT", settings.observability_langsmith_project)
    endpoint = optional_non_blank(settings.observability_langsmith_endpoint)
    set_or_clear_env("LANGSMITH_ENDPOINT", settings.observability_langsmith_endpoint)
    set_or_clear_env("LANGSMITH_API_KEY", settings.observability_langsmith_api_key)
    set_or_clear_bool_env("LANGSMITH_HIDE_INPUTS", settings.observability_langsmith_hide_inputs)
    set_or_clear_bool_env("LANGSMITH_HIDE_OUTPUTS", settings.observability_langsmith_hide_outputs)
    set_or_clear_bool_env(
        "LANGSMITH_HIDE_METADATA",
        settings.observability_langsmith_hide_metadata,
    )
    return endpoint


def set_or_clear_env(name: str, value: str) -> None:
    stripped = value.strip()
    if stripped:
        os.environ[name] = stripped
        return
    os.environ.pop(name, None)


def set_or_clear_bool_env(name: str, enabled: bool) -> None:
    if enabled:
        os.environ[name] = "true"
        return
    os.environ.pop(name, None)


def clear_langsmith_environment() -> None:
    for name in LANGSMITH_ENV_NAMES:
        os.environ.pop(name, None)


def parse_otlp_headers(values: list[str]) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        key, raw_value = value.split("=", 1)
        key = key.strip()
        if not key:
            continue
        headers[key] = raw_value.strip()
    return headers or None


def optional_non_blank(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def clean_span_attributes(
    attributes: Mapping[str, object | None],
) -> dict[str, SpanAttributeValue]:
    cleaned: dict[str, SpanAttributeValue] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if is_sensitive_attribute_key(key):
            cleaned[key] = REDACTED
            continue
        if isinstance(value, str | bool | int | float):
            cleaned[key] = redact_span_attribute_value(value)
        else:
            cleaned[key] = redact_span_attribute_value(str(redact_trace_payload(value)))
    return cleaned


def is_sensitive_attribute_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_").replace(".", "_")
    return any(part in normalized for part in SENSITIVE_ATTRIBUTE_KEY_PARTS)


def redact_span_attribute_value(value: str | bool | int | float) -> SpanAttributeValue:
    if not isinstance(value, str):
        return value
    redacted = SECRET_SHAPED_ATTRIBUTE_VALUE_RE.sub(redact_secret_match, value)
    return EMAIL_ATTRIBUTE_VALUE_RE.sub(REDACTED, redacted)


def redact_trace_payload(value: object) -> object:
    if isinstance(value, str | bool | int | float) or value is None:
        return redact_span_attribute_value(value) if isinstance(value, str) else value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {
            key: REDACTED if is_sensitive_attribute_key(str(key)) else redact_trace_payload(item)
            for key, item in mapping.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        sequence = cast(Sequence[object], value)
        return [redact_trace_payload(item) for item in sequence]
    return redact_span_attribute_value(str(value))


def redact_secret_match(match: re.Match[str]) -> str:
    text = match.group(0)
    if "=" in text:
        key, _value = text.split("=", 1)
        return f"{key}={REDACTED}"
    if ":" in text:
        key, _value = text.split(":", 1)
        return f"{key}:{REDACTED}"
    return REDACTED


@contextmanager
def trace_reactor_span(
    name: str,
    attributes: Mapping[str, object | None] | None = None,
) -> Generator[Span]:
    tracer = trace.get_tracer(REACTOR_TRACER_NAME)
    with tracer.start_as_current_span(
        name,
        attributes=clean_span_attributes(attributes or {}),
    ) as span:
        try:
            yield span
        except Exception as exc:
            redacted_message = str(redact_span_attribute_value(str(exc)))
            span.record_exception(RedactedTraceException(redacted_message))
            span.set_status(Status(StatusCode.ERROR, redacted_message))
            raise


class RedactedTraceException(Exception):
    pass
