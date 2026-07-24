from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.release.api_smoke import (
    REQUIRED_NEXT_ACTION_FIELDS,
    REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS,
    ApiHttpResult,
    DressApiSmokeConfig,
    main,
    next_action_schema_contract,
    run_dress_api_smoke,
)


def full_next_action_schema() -> dict[str, object]:
    return {
        "required": ["id", "label", "command"],
        "properties": {
            field: {"minLength": 1}
            if field in {"id", "label", "command"}
            else {"anyOf": [{"minLength": 1}, {"minItems": 1}, {"minProperties": 1}]}
            for field in REQUIRED_NEXT_ACTION_FIELDS
        },
    }


def simple_next_action_schema() -> dict[str, object]:
    return {
        "required": ["id", "label", "command"],
        "properties": {
            "id": {"minLength": 1},
            "label": {"minLength": 1},
            "command": {"minLength": 1},
        },
    }


def run_operator_next_action_schema() -> dict[str, object]:
    return {
        "required": ["id", "label", "command"],
        "properties": {
            field: {"minLength": 1} for field in REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS
        },
    }


def test_dress_api_smoke_verifies_health_ready_and_admin_capabilities() -> None:
    probe = FakeApiProbe(
        {
            "/healthz": ApiHttpResult(ok=True, status_code=200, body={"status": "ok"}),
            "/readyz": ApiHttpResult(ok=True, status_code=200, body={"status": "ready"}),
            "/api/admin/capabilities": ApiHttpResult(
                ok=True,
                status_code=200,
                body={"paths": ["/api/admin/capabilities", "/api/chat"]},
            ),
            "/openapi.json": ApiHttpResult(
                ok=True,
                status_code=200,
                body={
                    "openapi": "3.1.0",
                    "paths": {"/api/chat": {}, "/api/admin/capabilities": {}},
                    "components": {
                        "schemas": {
                            "ChatRequest": {},
                            "ChatResponse": {},
                            "FeedbackNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                    "candidateTag": {"anyOf": [{"minLength": 1}]},
                                    "caseFile": {"anyOf": [{"minLength": 1}]},
                                    "datasetName": {"anyOf": [{"minLength": 1}]},
                                    "envFileCommand": {"anyOf": [{"minLength": 1}]},
                                    "runFile": {"anyOf": [{"minLength": 1}]},
                                    "reportFile": {"anyOf": [{"minLength": 1}]},
                                    "suiteFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightEnvTemplate": {"anyOf": [{"minLength": 1}]},
                                    "replatformReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "smokePlanFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseEvidenceFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "readinessReportArg": {"anyOf": [{"minLength": 1}]},
                                    "readinessReports": {"anyOf": [{"minProperties": 1}]},
                                    "remediationCommand": {"anyOf": [{"minLength": 1}]},
                                    "requiredReadinessReports": {"anyOf": [{"minItems": 1}]},
                                    "requiredEnvAnyOf": {"anyOf": [{"minItems": 1}]},
                                    "recommendedEnv": {"anyOf": [{"minItems": 1}]},
                                },
                            },
                            "RagIngestionCandidateNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                    "candidateTag": {"anyOf": [{"minLength": 1}]},
                                    "caseFile": {"anyOf": [{"minLength": 1}]},
                                    "datasetName": {"anyOf": [{"minLength": 1}]},
                                    "envFileCommand": {"anyOf": [{"minLength": 1}]},
                                    "runFile": {"anyOf": [{"minLength": 1}]},
                                    "reportFile": {"anyOf": [{"minLength": 1}]},
                                    "suiteFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightEnvTemplate": {"anyOf": [{"minLength": 1}]},
                                    "replatformReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "smokePlanFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseEvidenceFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "readinessReportArg": {"anyOf": [{"minLength": 1}]},
                                    "readinessReports": {"anyOf": [{"minProperties": 1}]},
                                    "remediationCommand": {"anyOf": [{"minLength": 1}]},
                                    "requiredReadinessReports": {"anyOf": [{"minItems": 1}]},
                                    "requiredEnvAnyOf": {"anyOf": [{"minItems": 1}]},
                                    "recommendedEnv": {"anyOf": [{"minItems": 1}]},
                                },
                            },
                            "MemoryNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                },
                            },
                            "RunOperatorNextAction": run_operator_next_action_schema(),
                        }
                    },
                },
            ),
        }
    )

    report = run_dress_api_smoke(
        DressApiSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_API_KEY": "api-secret"},
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "dress_rehearsal",
        "base_url": "https://reactor.example",
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
            },
            "healthz": {"status": "passed", "status_code": 200},
            "readyz": {"status": "passed", "status_code": 200},
            "admin_capabilities": {
                "status": "passed",
                "status_code": 200,
                "path_count": 2,
            },
            "openapi": {
                "status": "passed",
                "status_code": 200,
                "openapi_version": "3.1.0",
                "path_count": 2,
                "schema_count": 6,
                "next_action_schemas": [
                    "FeedbackNextAction",
                    "RagIngestionCandidateNextAction",
                    "MemoryNextAction",
                    "RunOperatorNextAction",
                ],
                "next_action_schema_fields": list(REQUIRED_NEXT_ACTION_FIELDS),
                "run_operator_next_action_schema_fields": list(
                    REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS
                ),
                "next_action_fields_non_empty": True,
            },
        },
        "evidence": {
            "artifact": "reports/full-backup-db-api-dress-rehearsal.json",
            "owner": "reactor.release",
            "mode": "dress_api_smoke",
            "apiBoundary": {
                "status": "verified",
                "framework": "FastAPI",
                "schema": "OpenAPI",
                "validation": "Pydantic",
                "openapiPath": "/openapi.json",
                "openapiVersion": "3.1.0",
                "routeCount": 2,
                "schemaCount": 6,
                "requiredPaths": ["/api/admin/capabilities", "/api/chat"],
                "nextActionSchemas": [
                    "FeedbackNextAction",
                    "RagIngestionCandidateNextAction",
                    "MemoryNextAction",
                    "RunOperatorNextAction",
                ],
                "nextActionSchemaFields": list(REQUIRED_NEXT_ACTION_FIELDS),
                "runOperatorNextActionSchemaFields": list(REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS),
                "nextActionFieldsNonEmpty": True,
                "requestResponseModels": True,
                "publicMetadataAllowlist": True,
                "chatPolicyBoundary": {
                    "invokeAndStreamSharedRunService": True,
                    "sharedRunServiceComponents": [
                        "tool_provider",
                        "tool_handler",
                        "tool_invocation_store",
                        "builtin_tool_specs",
                    ],
                    "verificationSensors": [
                        "uv run pytest tests/integration/test_chat_api.py -q "
                        "-k 'chat_request_uses_reactor_tool_policy_components or "
                        "chat_stream_uses_reactor_tool_policy_components'"
                    ],
                    "covers": [
                        "chat_invoke_shares_reactor_tool_policy_components",
                        "chat_stream_shares_reactor_tool_policy_components",
                    ],
                },
                "secretFree": True,
            },
        },
    }
    openapi_check = report["checks"]["openapi"]
    assert "candidateTag" in openapi_check["next_action_schema_fields"]
    api_boundary = report["evidence"]["apiBoundary"]
    assert "candidateTag" in api_boundary["nextActionSchemaFields"]
    assert probe.calls == [
        ("/healthz", {}),
        ("/readyz", {}),
        ("/api/admin/capabilities", {"X-Reactor-API-Key": "api-secret"}),
        ("/openapi.json", {}),
    ]


def test_api_smoke_next_action_contract_requires_run_recovery_metadata() -> None:
    contract = next_action_schema_contract(
        {
            "FeedbackNextAction": full_next_action_schema(),
            "RagIngestionCandidateNextAction": full_next_action_schema(),
            "MemoryNextAction": simple_next_action_schema(),
            "RunOperatorNextAction": simple_next_action_schema(),
        }
    )

    assert contract["next_action_fields_non_empty"] is False


def test_dress_api_smoke_skips_when_required_env_is_missing() -> None:
    report = run_dress_api_smoke(
        DressApiSmokeConfig(base_url=""),
        http_probe=FakeApiProbe({}),
        environ={},
    )

    assert report == {
        "ok": False,
        "status": "skipped",
        "scope": "dress_rehearsal",
        "checks": {
            "required_env": {
                "status": "failed",
                "variables": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
                "missing": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
            }
        },
        "error": "missing required API smoke environment",
        "nextActions": [
            {
                "id": "configure_api_smoke_env",
                "label": "Configure API smoke environment",
                "command": (
                    "REACTOR_API_BASE_URL=<api-url> REACTOR_API_KEY=<api-key> "
                    "uv run reactor-dress-api-smoke --output "
                    "reports/full-backup-db-api-dress-rehearsal.json"
                ),
                "requiredEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
                "missingEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
                "reportFile": "reports/full-backup-db-api-dress-rehearsal.json",
            }
        ],
    }


def test_dress_api_smoke_fails_when_next_action_schema_contract_is_missing() -> None:
    probe = FakeApiProbe(
        {
            "/healthz": ApiHttpResult(ok=True, status_code=200, body={"status": "ok"}),
            "/readyz": ApiHttpResult(ok=True, status_code=200, body={"status": "ready"}),
            "/api/admin/capabilities": ApiHttpResult(
                ok=True,
                status_code=200,
                body={"paths": ["/api/admin/capabilities", "/api/chat"]},
            ),
            "/openapi.json": ApiHttpResult(
                ok=True,
                status_code=200,
                body={
                    "openapi": "3.1.0",
                    "paths": {"/api/chat": {}, "/api/admin/capabilities": {}},
                    "components": {
                        "schemas": {
                            "FeedbackNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                },
                            }
                        }
                    },
                },
            ),
        }
    )

    report = run_dress_api_smoke(
        DressApiSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_API_KEY": "api-secret"},
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["openapi"]["status"] == "failed"
    assert report["checks"]["openapi"]["error"] == "next action schema contract missing"


def test_dress_api_smoke_records_sanitized_admin_failure() -> None:
    report = run_dress_api_smoke(
        DressApiSmokeConfig(base_url="https://reactor.example"),
        http_probe=FakeApiProbe(
            {
                "/healthz": ApiHttpResult(ok=True, status_code=200, body={"status": "ok"}),
                "/readyz": ApiHttpResult(ok=True, status_code=200, body={"status": "ready"}),
                "/api/admin/capabilities": ApiHttpResult(
                    ok=False,
                    status_code=403,
                    error="denied api-secret",
                ),
            }
        ),
        environ={"REACTOR_API_KEY": "api-secret"},
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["admin_capabilities"] == {
        "status": "failed",
        "status_code": 403,
        "error": "denied [redacted]",
    }


def test_dress_api_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "api-smoke.json"

    monkeypatch.setenv("REACTOR_API_BASE_URL", "https://reactor.example")
    monkeypatch.setenv("REACTOR_API_KEY", "api-secret")
    monkeypatch.setattr("reactor.release.api_smoke.HttpApiProbe", fake_http_api_probe)

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["ok"] is True


def test_dress_api_smoke_cli_writes_missing_env_next_action(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output_path = tmp_path / "reports" / "release" / "api-smoke.json"
    monkeypatch.delenv("REACTOR_API_BASE_URL", raising=False)
    monkeypatch.delenv("REACTOR_API_KEY", raising=False)

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 1
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "skipped"
    assert report["nextActions"] == [
        {
            "id": "configure_api_smoke_env",
            "label": "Configure API smoke environment",
            "command": (
                "REACTOR_API_BASE_URL=<api-url> REACTOR_API_KEY=<api-key> "
                "uv run reactor-dress-api-smoke --output "
                "reports/full-backup-db-api-dress-rehearsal.json"
            ),
            "requiredEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
            "missingEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
            "reportFile": "reports/full-backup-db-api-dress-rehearsal.json",
        }
    ]


class FakeApiProbe:
    def __init__(self, results: dict[str, ApiHttpResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> ApiHttpResult:
        self.calls.append((path, headers))
        return self._results[path]


def fake_http_api_probe(**_: object) -> FakeApiProbe:
    return FakeApiProbe(
        {
            "/healthz": ApiHttpResult(ok=True, status_code=200, body={"status": "ok"}),
            "/readyz": ApiHttpResult(ok=True, status_code=200, body={"status": "ready"}),
            "/api/admin/capabilities": ApiHttpResult(
                ok=True,
                status_code=200,
                body={"paths": ["/api/admin/capabilities"]},
            ),
            "/openapi.json": ApiHttpResult(
                ok=True,
                status_code=200,
                body={
                    "openapi": "3.1.0",
                    "paths": {"/api/admin/capabilities": {}, "/api/chat": {}},
                    "components": {
                        "schemas": {
                            "ChatRequest": {},
                            "ChatResponse": {},
                            "FeedbackNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                    "candidateTag": {"anyOf": [{"minLength": 1}]},
                                    "caseFile": {"anyOf": [{"minLength": 1}]},
                                    "datasetName": {"anyOf": [{"minLength": 1}]},
                                    "envFileCommand": {"anyOf": [{"minLength": 1}]},
                                    "runFile": {"anyOf": [{"minLength": 1}]},
                                    "reportFile": {"anyOf": [{"minLength": 1}]},
                                    "suiteFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightEnvTemplate": {"anyOf": [{"minLength": 1}]},
                                    "replatformReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "smokePlanFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseEvidenceFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "readinessReportArg": {"anyOf": [{"minLength": 1}]},
                                    "readinessReports": {"anyOf": [{"minProperties": 1}]},
                                    "remediationCommand": {"anyOf": [{"minLength": 1}]},
                                    "requiredReadinessReports": {"anyOf": [{"minItems": 1}]},
                                    "requiredEnvAnyOf": {"anyOf": [{"minItems": 1}]},
                                    "recommendedEnv": {"anyOf": [{"minItems": 1}]},
                                },
                            },
                            "RagIngestionCandidateNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                    "candidateTag": {"anyOf": [{"minLength": 1}]},
                                    "caseFile": {"anyOf": [{"minLength": 1}]},
                                    "datasetName": {"anyOf": [{"minLength": 1}]},
                                    "envFileCommand": {"anyOf": [{"minLength": 1}]},
                                    "runFile": {"anyOf": [{"minLength": 1}]},
                                    "reportFile": {"anyOf": [{"minLength": 1}]},
                                    "suiteFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightFile": {"anyOf": [{"minLength": 1}]},
                                    "preflightEnvTemplate": {"anyOf": [{"minLength": 1}]},
                                    "replatformReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "smokePlanFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseEvidenceFile": {"anyOf": [{"minLength": 1}]},
                                    "releaseReadinessFile": {"anyOf": [{"minLength": 1}]},
                                    "readinessReportArg": {"anyOf": [{"minLength": 1}]},
                                    "readinessReports": {"anyOf": [{"minProperties": 1}]},
                                    "remediationCommand": {"anyOf": [{"minLength": 1}]},
                                    "requiredReadinessReports": {"anyOf": [{"minItems": 1}]},
                                    "requiredEnvAnyOf": {"anyOf": [{"minItems": 1}]},
                                    "recommendedEnv": {"anyOf": [{"minItems": 1}]},
                                },
                            },
                            "MemoryNextAction": {
                                "required": ["id", "label", "command"],
                                "properties": {
                                    "id": {"minLength": 1},
                                    "label": {"minLength": 1},
                                    "command": {"minLength": 1},
                                },
                            },
                            "RunOperatorNextAction": run_operator_next_action_schema(),
                        }
                    },
                },
            ),
        }
    )
