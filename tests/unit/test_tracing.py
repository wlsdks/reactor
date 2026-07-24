from __future__ import annotations

import os

import pytest

from reactor.core.settings import Settings
from reactor.observability.tracing import (
    clean_span_attributes,
    configure_tracing,
    shutdown_tracing,
    trace_reactor_span,
)


def test_clean_span_attributes_keeps_otel_safe_values() -> None:
    attributes = clean_span_attributes(
        {
            "reactor.run_id": "run_1",
            "reactor.tool_calls": 3,
            "reactor.cost": 0.25,
            "reactor.cached": False,
            "reactor.none": None,
            "reactor.payload": {"nested": "value"},
        }
    )

    assert attributes == {
        "reactor.run_id": "run_1",
        "reactor.tool_calls": 3,
        "reactor.cost": 0.25,
        "reactor.cached": False,
        "reactor.payload": "{'nested': 'value'}",
    }


def test_clean_span_attributes_redacts_secret_keys_and_values() -> None:
    attributes = clean_span_attributes(
        {
            "reactor.api_key": "sk-live-1234567890abcdef",
            "reactor.request": {
                "password": "correct-horse-battery-staple",
                "query": "investigate api_key=sk-live-1234567890abcdef",
            },
            "reactor.safe": "plain text",
        }
    )

    encoded = str(attributes)
    assert attributes["reactor.api_key"] == "[REDACTED]"
    assert "correct-horse-battery-staple" not in encoded
    assert "sk-live-1234567890abcdef" not in encoded
    assert "api_key=[REDACTED]" in encoded
    assert attributes["reactor.safe"] == "plain text"


def test_trace_reactor_span_records_exception_status(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = RecordingTracer()

    def get_tracer(name: str) -> RecordingTracer:
        _ = name
        return tracer

    monkeypatch.setattr("reactor.observability.tracing.trace.get_tracer", get_tracer)

    with pytest.raises(ValueError, match="boom"):
        with trace_reactor_span("reactor.test", {"reactor.run_id": "run_1"}):
            raise ValueError("boom")

    assert tracer.started == [
        ("reactor.test", {"reactor.run_id": "run_1"}),
    ]
    assert tracer.span.exceptions == ["boom"]
    assert tracer.span.status_code == "ERROR"


def test_trace_reactor_span_redacts_exception_status_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = RecordingTracer()

    def get_tracer(name: str) -> RecordingTracer:
        _ = name
        return tracer

    monkeypatch.setattr("reactor.observability.tracing.trace.get_tracer", get_tracer)

    with pytest.raises(RuntimeError):
        with trace_reactor_span("reactor.test", {"reactor.run_id": "run_1"}):
            raise RuntimeError(
                "provider failed for sample-user@example.com with api_key=sk-live-1234567890abcdef"
            )

    assert tracer.span.status_code == "ERROR"
    assert tracer.span.status_description is not None
    assert "sample-user@example.com" not in tracer.span.status_description
    assert "sk-live-1234567890abcdef" not in tracer.span.status_description
    assert "[REDACTED]" in tracer.span.status_description
    assert len(tracer.span.exceptions) == 1
    assert "sample-user@example.com" not in tracer.span.exceptions[0]
    assert "sk-live-1234567890abcdef" not in tracer.span.exceptions[0]
    assert "[REDACTED]" in tracer.span.exceptions[0]


def test_configure_tracing_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[object] = []
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "stale-project")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://stale.example")
    monkeypatch.setenv("LANGSMITH_API_KEY", "stale-key")
    monkeypatch.setenv("LANGSMITH_HIDE_INPUTS", "true")
    monkeypatch.setenv("LANGSMITH_HIDE_OUTPUTS", "true")
    monkeypatch.setenv("LANGSMITH_HIDE_METADATA", "true")
    monkeypatch.setattr(
        "reactor.observability.tracing.trace.set_tracer_provider", configured.append
    )

    result = configure_tracing(Settings(observability_tracing_enabled=False))

    assert result.enabled is False
    assert result.exporter == "none"
    assert configured == []
    assert "LANGSMITH_TRACING" not in os.environ
    assert "LANGSMITH_PROJECT" not in os.environ
    assert "LANGSMITH_ENDPOINT" not in os.environ
    assert "LANGSMITH_API_KEY" not in os.environ
    assert "LANGSMITH_HIDE_INPUTS" not in os.environ
    assert "LANGSMITH_HIDE_OUTPUTS" not in os.environ
    assert "LANGSMITH_HIDE_METADATA" not in os.environ


def test_configure_tracing_wires_otlp_http_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[FakeTracerProvider] = []
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "stale-project")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://stale.example")
    monkeypatch.setenv("LANGSMITH_API_KEY", "stale-key")
    monkeypatch.setenv("LANGSMITH_HIDE_INPUTS", "true")
    monkeypatch.setenv("LANGSMITH_HIDE_OUTPUTS", "true")
    monkeypatch.setenv("LANGSMITH_HIDE_METADATA", "true")

    monkeypatch.setattr("reactor.observability.tracing.Resource", FakeResource)
    monkeypatch.setattr("reactor.observability.tracing.TracerProvider", FakeTracerProvider)
    monkeypatch.setattr("reactor.observability.tracing.BatchSpanProcessor", FakeSpanProcessor)
    monkeypatch.setattr("reactor.observability.tracing.OTLPSpanExporter", FakeOtlpExporter)
    monkeypatch.setattr("reactor.observability.tracing.TraceIdRatioBased", FakeSampler)
    monkeypatch.setattr(
        "reactor.observability.tracing.trace.set_tracer_provider", configured.append
    )

    result = configure_tracing(
        Settings(
            app_name="Reactor",
            environment="production",
            observability_tracing_enabled=True,
            observability_trace_exporter="otlp_http",
            observability_otlp_endpoint="https://otel.example/v1/traces",
            observability_otlp_headers=["x-api-key=secret", "tenant=reactor"],
            observability_trace_sample_ratio=0.75,
        )
    )

    assert result.enabled is True
    assert result.exporter == "otlp_http"
    assert result.endpoint == "https://otel.example/v1/traces"
    assert len(configured) == 1
    provider = configured[0]
    assert provider.resource.attributes == {
        "service.name": "Reactor",
        "deployment.environment": "production",
    }
    assert provider.sampler.arg == 0.75
    assert provider.processors == [
        FakeSpanProcessor(
            FakeOtlpExporter(
                endpoint="https://otel.example/v1/traces",
                headers={"x-api-key": "secret", "tenant": "reactor"},
            )
        )
    ]
    assert "LANGSMITH_TRACING" not in os.environ
    assert "LANGSMITH_PROJECT" not in os.environ
    assert "LANGSMITH_ENDPOINT" not in os.environ
    assert "LANGSMITH_API_KEY" not in os.environ
    assert "LANGSMITH_HIDE_INPUTS" not in os.environ
    assert "LANGSMITH_HIDE_OUTPUTS" not in os.environ
    assert "LANGSMITH_HIDE_METADATA" not in os.environ


def test_shutdown_tracing_flushes_and_shuts_down_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeShutdownTracerProvider()
    monkeypatch.setattr("reactor.observability.tracing._configured_tracer_provider", provider)

    shutdown_tracing()

    assert provider.calls == ["force_flush", "shutdown"]
    shutdown_tracing()
    assert provider.calls == ["force_flush", "shutdown"]


def test_configure_tracing_wires_langsmith_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[object] = []
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.delenv("LANGSMITH_ENDPOINT", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_HIDE_INPUTS", raising=False)
    monkeypatch.delenv("LANGSMITH_HIDE_OUTPUTS", raising=False)
    monkeypatch.delenv("LANGSMITH_HIDE_METADATA", raising=False)
    monkeypatch.setattr(
        "reactor.observability.tracing.trace.set_tracer_provider", configured.append
    )

    result = configure_tracing(
        Settings(
            observability_tracing_enabled=True,
            observability_trace_exporter="langsmith",
            observability_langsmith_project="reactor-prod",
            observability_langsmith_endpoint="https://api.smith.langchain.com",
            observability_langsmith_api_key="lsv2_secret",
        )
    )

    assert result.enabled is True
    assert result.exporter == "langsmith"
    assert result.endpoint == "https://api.smith.langchain.com"
    assert configured == []
    assert {
        "LANGSMITH_TRACING": "true",
        "LANGSMITH_PROJECT": "reactor-prod",
        "LANGSMITH_ENDPOINT": "https://api.smith.langchain.com",
        "LANGSMITH_API_KEY": "lsv2_secret",
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
        "LANGSMITH_HIDE_METADATA": "true",
    }.items() <= dict(os.environ).items()


def test_configure_tracing_clears_blank_langsmith_optional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_PROJECT", "stale-project")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://stale.example")
    monkeypatch.setenv("LANGSMITH_API_KEY", "stale-key")

    result = configure_tracing(
        Settings(
            observability_tracing_enabled=True,
            observability_trace_exporter="langsmith",
            observability_langsmith_project="",
            observability_langsmith_endpoint="",
            observability_langsmith_api_key="",
        )
    )

    assert result.enabled is True
    assert result.exporter == "langsmith"
    assert result.endpoint is None
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert "LANGSMITH_PROJECT" not in os.environ
    assert "LANGSMITH_ENDPOINT" not in os.environ
    assert "LANGSMITH_API_KEY" not in os.environ


class RecordingSpan:
    def __init__(self) -> None:
        self.exceptions: list[str] = []
        self.status_code: str | None = None
        self.status_description: str | None = None

    def record_exception(self, exception: BaseException) -> None:
        self.exceptions.append(str(exception))

    def set_status(self, status: object) -> None:
        self.status_code = getattr(getattr(status, "status_code", None), "name", None)
        self.status_description = getattr(status, "description", None)


class RecordingSpanContext:
    def __init__(self, span: RecordingSpan) -> None:
        self._span = span

    def __enter__(self) -> RecordingSpan:
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        _ = exc_type, exc, traceback
        return False


class RecordingTracer:
    def __init__(self) -> None:
        self.span = RecordingSpan()
        self.started: list[tuple[str, dict[str, str | bool | int | float]]] = []

    def start_as_current_span(
        self,
        name: str,
        *,
        attributes: dict[str, str | bool | int | float] | None = None,
    ) -> RecordingSpanContext:
        self.started.append((name, attributes or {}))
        return RecordingSpanContext(self.span)


class FakeResource:
    def __init__(self, attributes: dict[str, object]) -> None:
        self.attributes = attributes

    @classmethod
    def create(cls, attributes: dict[str, object]) -> FakeResource:
        return cls(attributes)


class FakeSampler:
    def __init__(self, arg: float) -> None:
        self.arg = arg


class FakeTracerProvider:
    def __init__(self, *, resource: FakeResource, sampler: FakeSampler) -> None:
        self.resource = resource
        self.sampler = sampler
        self.processors: list[FakeSpanProcessor] = []
        self.closed = False

    def add_span_processor(self, processor: FakeSpanProcessor) -> None:
        self.processors.append(processor)

    def force_flush(self) -> bool:
        return True

    def shutdown(self) -> None:
        self.closed = True


class FakeShutdownTracerProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def force_flush(self) -> bool:
        self.calls.append("force_flush")
        return True

    def shutdown(self) -> None:
        self.calls.append("shutdown")


class FakeSpanProcessor:
    def __init__(self, exporter: object) -> None:
        self.exporter = exporter

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeSpanProcessor) and self.exporter == other.exporter


class FakeOtlpExporter:
    def __init__(self, *, endpoint: str | None, headers: dict[str, str] | None) -> None:
        self.endpoint = endpoint
        self.headers = headers or {}

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FakeOtlpExporter)
            and self.endpoint == other.endpoint
            and self.headers == other.headers
        )
