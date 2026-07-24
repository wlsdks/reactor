from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from reactor.release.readiness import write_report

REQUIRED_LOCAL_API_CHAT_SMOKE_ENV = ("REACTOR_API_BASE_URL",)


@dataclass(frozen=True)
class LocalApiChatSmokeConfig:
    base_url: str = ""
    provider: str = ""
    model: str = ""
    message: str = "Reply with exactly: pong"
    expected_content: str = "pong"
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class ApiChatHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | None = None
    error: str | None = None


class ApiChatProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> ApiChatHttpResult: ...

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> ApiChatHttpResult: ...


class HttpApiChatProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> ApiChatHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return ApiChatHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> ApiChatHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            return result_from_response(response)
        except httpx.HTTPError as error:
            return ApiChatHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> ApiChatHttpResult:
    if response.status_code >= 400:
        return ApiChatHttpResult(ok=False, status_code=response.status_code, error=response.text)
    try:
        body = response.json()
    except ValueError:
        return ApiChatHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    if not isinstance(body, dict):
        return ApiChatHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    return ApiChatHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object], body),
    )


def run_local_api_chat_smoke(
    config: LocalApiChatSmokeConfig,
    *,
    http_probe: ApiChatProbe,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    base_url = config.base_url.strip() or environ.get("REACTOR_API_BASE_URL", "").strip()
    if not base_url:
        return {
            "ok": False,
            "status": "skipped",
            "scope": "local_contract",
            "checks": {
                "required_env": {
                    "status": "failed",
                    "variables": list(REQUIRED_LOCAL_API_CHAT_SMOKE_ENV),
                    "missing": list(REQUIRED_LOCAL_API_CHAT_SMOKE_ENV),
                }
            },
            "error": "missing required local API chat smoke environment",
        }

    report: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "scope": "local_contract",
        "base_url": base_url,
        "provider": config.provider,
        "model": config.model,
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": list(REQUIRED_LOCAL_API_CHAT_SMOKE_ENV),
            }
        },
    }

    health = http_probe.get_json("/healthz", headers={})
    report["checks"]["healthz"] = basic_check_report(health, environ)
    if report["checks"]["healthz"]["status"] != "passed":
        return report

    ready = http_probe.get_json("/readyz", headers={})
    report["checks"]["readyz"] = ready_check_report(ready, environ)
    if report["checks"]["readyz"]["status"] != "passed":
        return report

    chat = http_probe.post_json(
        "/api/chat",
        headers={
            "Content-Type": "application/json",
            "X-Reactor-User-Id": "release-smoke",
            "X-Reactor-Tenant-Id": "local",
        },
        payload=chat_payload(config),
    )
    report["checks"]["chat"] = chat_check_report(chat, config, environ)
    if report["checks"]["chat"]["status"] != "passed":
        return report

    report["ok"] = True
    report["status"] = "passed"
    return report


def chat_payload(config: LocalApiChatSmokeConfig) -> dict[str, object]:
    payload: dict[str, object] = {
        "message": config.message,
        "metadata": {"sessionId": "local-api-chat-smoke"},
    }
    if config.provider.strip():
        payload["modelProvider"] = config.provider.strip()
    if config.model.strip():
        payload["model"] = config.model.strip()
    return payload


def basic_check_report(result: ApiChatHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok:
        return failed_check(result, environ)
    return {"status": "passed", "status_code": result.status_code}


def ready_check_report(result: ApiChatHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_check(result, environ)
    if result.body.get("status") != "ready":
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "api is not ready",
        }
    return {"status": "passed", "status_code": result.status_code}


def chat_check_report(
    result: ApiChatHttpResult,
    config: LocalApiChatSmokeConfig,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_check(result, environ)
    success = result.body.get("success")
    content = result.body.get("content")
    if success is not True or not isinstance(content, str):
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "chat response did not succeed",
        }
    expected_content = config.expected_content.strip()
    if expected_content and expected_content not in content:
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "expected content not found",
            "content_preview": sanitize_error(content[:200], environ),
        }
    metadata = result.body.get("metadata")
    typed_metadata = cast(dict[str, object], metadata) if isinstance(metadata, dict) else {}
    run_id_present = bool(typed_metadata.get("runId"))
    return {
        "status": "passed",
        "status_code": result.status_code,
        "content_length": len(content),
        "run_id_present": run_id_present,
    }


def failed_check(result: ApiChatHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    return {
        "status": "failed",
        "status_code": result.status_code,
        "error": sanitize_error(result.error or "request_failed", environ),
    }


def sanitize_error(message: str, environ: Mapping[str, str]) -> str:
    sanitized = message
    for value in environ.values():
        if value and len(value) >= 6:
            sanitized = sanitized.replace(value, "[redacted]")
    return sanitized


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Reactor API chat smoke check.")
    parser.add_argument("--base-url", default="", help="Reactor API base URL; falls back to env")
    parser.add_argument("--provider", default="", help="Optional chat model provider")
    parser.add_argument("--model", default="", help="Optional chat model")
    parser.add_argument("--message", default="Reply with exactly: pong", help="Smoke prompt")
    parser.add_argument("--expected-content", default="pong", help="Expected response content")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = str(args.base_url).strip() or os.environ.get("REACTOR_API_BASE_URL", "").strip()
    config = LocalApiChatSmokeConfig(
        base_url=base_url,
        provider=str(args.provider).strip(),
        model=str(args.model).strip(),
        message=str(args.message),
        expected_content=str(args.expected_content),
        timeout_seconds=float(args.timeout_seconds),
    )
    report = run_local_api_chat_smoke(
        config,
        http_probe=HttpApiChatProbe(base_url=base_url, timeout_seconds=config.timeout_seconds),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
