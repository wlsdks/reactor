from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.release.api_chat_smoke import (
    ApiChatHttpResult,
    LocalApiChatSmokeConfig,
    main,
    run_local_api_chat_smoke,
)


def test_local_api_chat_smoke_verifies_health_ready_and_chat() -> None:
    probe = FakeApiChatProbe(
        {
            ("GET", "/healthz"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={"status": "ok"},
            ),
            ("GET", "/readyz"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={"status": "ready"},
            ),
            ("POST", "/api/chat"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={
                    "success": True,
                    "content": "pong",
                    "metadata": {"runId": "run_1"},
                },
            ),
        }
    )

    report = run_local_api_chat_smoke(
        LocalApiChatSmokeConfig(
            base_url="http://127.0.0.1:8010",
            provider="ollama",
            model="gemma4:12b",
            message="Reply with exactly: pong",
            expected_content="pong",
        ),
        http_probe=probe,
        environ={},
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "local_contract",
        "base_url": "http://127.0.0.1:8010",
        "provider": "ollama",
        "model": "gemma4:12b",
        "checks": {
            "required_env": {"status": "passed", "variables": ["REACTOR_API_BASE_URL"]},
            "healthz": {"status": "passed", "status_code": 200},
            "readyz": {"status": "passed", "status_code": 200},
            "chat": {
                "status": "passed",
                "status_code": 200,
                "content_length": 4,
                "run_id_present": True,
            },
        },
    }
    assert probe.calls == [
        ("GET", "/healthz", {}, None),
        ("GET", "/readyz", {}, None),
        (
            "POST",
            "/api/chat",
            {
                "Content-Type": "application/json",
                "X-Reactor-User-Id": "release-smoke",
                "X-Reactor-Tenant-Id": "local",
            },
            {
                "message": "Reply with exactly: pong",
                "metadata": {"sessionId": "local-api-chat-smoke"},
                "modelProvider": "ollama",
                "model": "gemma4:12b",
            },
        ),
    ]


def test_local_api_chat_smoke_skips_without_base_url() -> None:
    report = run_local_api_chat_smoke(
        LocalApiChatSmokeConfig(base_url=""),
        http_probe=FakeApiChatProbe({}),
        environ={},
    )

    assert report == {
        "ok": False,
        "status": "skipped",
        "scope": "local_contract",
        "checks": {
            "required_env": {
                "status": "failed",
                "variables": ["REACTOR_API_BASE_URL"],
                "missing": ["REACTOR_API_BASE_URL"],
            }
        },
        "error": "missing required local API chat smoke environment",
    }


def test_local_api_chat_smoke_records_sanitized_chat_failure() -> None:
    report = run_local_api_chat_smoke(
        LocalApiChatSmokeConfig(
            base_url="http://127.0.0.1:8010",
            expected_content="pong",
        ),
        http_probe=FakeApiChatProbe(
            {
                ("GET", "/healthz"): ApiChatHttpResult(
                    ok=True,
                    status_code=200,
                    body={"status": "ok"},
                ),
                ("GET", "/readyz"): ApiChatHttpResult(
                    ok=True,
                    status_code=200,
                    body={"status": "ready"},
                ),
                ("POST", "/api/chat"): ApiChatHttpResult(
                    ok=True,
                    status_code=200,
                    body={"success": True, "content": "wrong api-secret"},
                ),
            }
        ),
        environ={"REACTOR_API_KEY": "api-secret"},
    )

    assert report["ok"] is False
    assert report["checks"]["chat"] == {
        "status": "failed",
        "status_code": 200,
        "error": "expected content not found",
        "content_preview": "wrong [redacted]",
    }


def test_local_api_chat_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "api-chat-smoke.json"

    monkeypatch.setenv("REACTOR_API_BASE_URL", "http://127.0.0.1:8010")
    monkeypatch.setattr("reactor.release.api_chat_smoke.HttpApiChatProbe", fake_probe_factory)

    exit_code = main(
        [
            "--provider",
            "ollama",
            "--model",
            "gemma4:12b",
            "--expected-content",
            "pong",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["provider"] == "ollama"
    assert payload["model"] == "gemma4:12b"


class FakeApiChatProbe:
    def __init__(self, results: dict[tuple[str, str], ApiChatHttpResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> ApiChatHttpResult:
        self.calls.append(("GET", path, headers, None))
        return self._results[("GET", path)]

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> ApiChatHttpResult:
        self.calls.append(("POST", path, headers, payload))
        return self._results[("POST", path)]


def fake_probe_factory(**_: object) -> FakeApiChatProbe:
    return FakeApiChatProbe(
        {
            ("GET", "/healthz"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={"status": "ok"},
            ),
            ("GET", "/readyz"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={"status": "ready"},
            ),
            ("POST", "/api/chat"): ApiChatHttpResult(
                ok=True,
                status_code=200,
                body={"success": True, "content": "pong", "metadata": {"runId": "run_1"}},
            ),
        }
    )
