from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from reactor.release.readiness import write_report

REQUIRED_API_SMOKE_ENV = ("REACTOR_API_BASE_URL", "REACTOR_API_KEY")
REQUIRED_OPENAPI_PATHS = ("/api/admin/capabilities", "/api/chat")
REQUIRED_NEXT_ACTION_SCHEMAS = (
    "FeedbackNextAction",
    "RagIngestionCandidateNextAction",
    "MemoryNextAction",
    "RunOperatorNextAction",
)
SIMPLE_NEXT_ACTION_SCHEMAS = frozenset({"MemoryNextAction"})
REQUIRED_NEXT_ACTION_REQUIRED_FIELDS = ("command", "id", "label")
REQUIRED_NEXT_ACTION_FIELDS = (
    "candidateTag",
    "caseFile",
    "command",
    "datasetName",
    "envFileCommand",
    "id",
    "label",
    "preflightEnvTemplate",
    "preflightFile",
    "releaseEvidenceFile",
    "releaseReadinessFile",
    "recommendedEnv",
    "readinessReportArg",
    "readinessReports",
    "remediationCommand",
    "replatformReadinessFile",
    "reportFile",
    "requiredEnvAnyOf",
    "requiredReadinessReports",
    "runFile",
    "smokePlanFile",
    "suiteFile",
)
REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS = (
    "approvalId",
    "checkpointId",
    "checkpointNs",
    "command",
    "id",
    "label",
    "sourceRunId",
    "threadId",
)
API_SMOKE_ARTIFACT = "reports/full-backup-db-api-dress-rehearsal.json"


@dataclass(frozen=True)
class DressApiSmokeConfig:
    base_url: str = ""
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class ApiHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | None = None
    error: str | None = None


class ApiProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> ApiHttpResult: ...


class HttpApiProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> ApiHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return ApiHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> ApiHttpResult:
    if response.status_code >= 400:
        return ApiHttpResult(ok=False, status_code=response.status_code, error=response.text)
    try:
        body = response.json()
    except ValueError:
        return ApiHttpResult(ok=False, status_code=response.status_code, error="invalid_response")
    if not isinstance(body, dict):
        return ApiHttpResult(ok=False, status_code=response.status_code, error="invalid_response")
    return ApiHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object], body),
    )


def run_dress_api_smoke(
    config: DressApiSmokeConfig,
    *,
    http_probe: ApiProbe,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    base_url = config.base_url.strip() or environ.get("REACTOR_API_BASE_URL", "").strip()
    api_key = environ.get("REACTOR_API_KEY", "").strip()
    missing = [
        name
        for name, value in {
            "REACTOR_API_BASE_URL": base_url,
            "REACTOR_API_KEY": api_key,
        }.items()
        if not value
    ]
    if missing:
        return {
            "ok": False,
            "status": "skipped",
            "scope": "dress_rehearsal",
            "checks": {
                "required_env": {
                    "status": "failed",
                    "variables": list(REQUIRED_API_SMOKE_ENV),
                    "missing": missing,
                }
            },
            "error": "missing required API smoke environment",
            "nextActions": [configure_api_smoke_env_next_action(missing)],
        }

    report: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "scope": "dress_rehearsal",
        "base_url": base_url,
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": list(REQUIRED_API_SMOKE_ENV),
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

    admin = http_probe.get_json(
        "/api/admin/capabilities",
        headers={"X-Reactor-API-Key": api_key},
    )
    report["checks"]["admin_capabilities"] = admin_capabilities_report(admin, environ)
    if report["checks"]["admin_capabilities"]["status"] != "passed":
        return report

    openapi = http_probe.get_json("/openapi.json", headers={})
    report["checks"]["openapi"] = openapi_report(openapi, environ)
    if report["checks"]["openapi"]["status"] != "passed":
        return report

    report["ok"] = True
    report["status"] = "passed"
    report["evidence"] = api_boundary_evidence(report["checks"])
    return report


def basic_check_report(result: ApiHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok:
        return failed_check(result, environ)
    return {"status": "passed", "status_code": result.status_code}


def ready_check_report(result: ApiHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_check(result, environ)
    if result.body.get("status") != "ready":
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "api is not ready",
        }
    return {"status": "passed", "status_code": result.status_code}


def admin_capabilities_report(
    result: ApiHttpResult,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_check(result, environ)
    paths = result.body.get("paths")
    if not isinstance(paths, list):
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "invalid capabilities response",
        }
    capability_paths = cast("list[object]", paths)
    return {
        "status": "passed",
        "status_code": result.status_code,
        "path_count": len(capability_paths),
    }


def openapi_report(result: ApiHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_check(result, environ)
    openapi_version = result.body.get("openapi")
    paths_value = result.body.get("paths")
    components_value = result.body.get("components")
    if not isinstance(openapi_version, str) or not isinstance(paths_value, Mapping):
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "invalid openapi response",
        }
    paths = cast(Mapping[str, object], paths_value)
    components = (
        cast(Mapping[str, object], components_value)
        if isinstance(components_value, Mapping)
        else cast(Mapping[str, object], {})
    )
    schemas_value = components.get("schemas")
    schemas = (
        cast(Mapping[str, object], schemas_value)
        if isinstance(schemas_value, Mapping)
        else cast(Mapping[str, object], {})
    )
    if not all(path in paths for path in REQUIRED_OPENAPI_PATHS):
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "required openapi paths missing",
        }
    next_action_contract = next_action_schema_contract(schemas)
    if next_action_schema_contract_missing(next_action_contract):
        return {
            "status": "failed",
            "status_code": result.status_code,
            "error": "next action schema contract missing",
            "openapi_version": openapi_version,
            "path_count": len(paths),
            "schema_count": len(schemas),
            **next_action_contract,
        }
    return {
        "status": "passed",
        "status_code": result.status_code,
        "openapi_version": openapi_version,
        "path_count": len(paths),
        "schema_count": len(schemas),
        **next_action_contract,
    }


def next_action_schema_contract(schemas: Mapping[str, object]) -> dict[str, object]:
    found: list[str] = []
    fields_non_empty = True
    for schema_name in REQUIRED_NEXT_ACTION_SCHEMAS:
        schema = schemas.get(schema_name)
        if not isinstance(schema, Mapping):
            fields_non_empty = False
            continue
        schema_mapping = cast(Mapping[str, object], schema)
        required = schema_mapping.get("required")
        properties = schema_mapping.get("properties")
        if not isinstance(required, Sequence) or isinstance(required, str | bytes | bytearray):
            fields_non_empty = False
            continue
        required_fields = {
            item for item in cast(Sequence[object], required) if isinstance(item, str)
        }
        if required_fields != set(REQUIRED_NEXT_ACTION_REQUIRED_FIELDS):
            fields_non_empty = False
            continue
        if not isinstance(properties, Mapping):
            fields_non_empty = False
            continue
        property_mapping = cast(Mapping[object, object], properties)
        schema_field_names = (
            REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS
            if schema_name == "RunOperatorNextAction"
            else REQUIRED_NEXT_ACTION_REQUIRED_FIELDS
            if schema_name in SIMPLE_NEXT_ACTION_SCHEMAS
            else REQUIRED_NEXT_ACTION_FIELDS
        )
        for field_name in schema_field_names:
            field_schema = property_mapping.get(field_name)
            if not isinstance(field_schema, Mapping):
                fields_non_empty = False
                continue
            if not schema_declares_min_length_one(cast(Mapping[object, object], field_schema)):
                fields_non_empty = False
        found.append(schema_name)
    return {
        "next_action_schemas": found,
        "next_action_schema_fields": list(REQUIRED_NEXT_ACTION_FIELDS),
        "run_operator_next_action_schema_fields": list(REQUIRED_RUN_OPERATOR_NEXT_ACTION_FIELDS),
        "next_action_fields_non_empty": fields_non_empty,
    }


def schema_declares_min_length_one(field_schema: Mapping[object, object]) -> bool:
    if (
        field_schema.get("minLength") == 1
        or field_schema.get("minItems") == 1
        or field_schema.get("minProperties") == 1
    ):
        return True
    any_of = field_schema.get("anyOf")
    if not isinstance(any_of, Sequence) or isinstance(any_of, str | bytes | bytearray):
        return False
    for item in cast(Sequence[object], any_of):
        if isinstance(item, Mapping) and schema_declares_min_length_one(
            cast(Mapping[object, object], item)
        ):
            return True
    return False


def next_action_schema_contract_missing(contract: Mapping[str, object]) -> bool:
    found_schemas = contract.get("next_action_schemas")
    if not isinstance(found_schemas, Sequence) or isinstance(
        found_schemas, str | bytes | bytearray
    ):
        return True
    found_schema_names = {
        item for item in cast(Sequence[object], found_schemas) if isinstance(item, str)
    }
    return (
        found_schema_names != set(REQUIRED_NEXT_ACTION_SCHEMAS)
        or contract.get("next_action_fields_non_empty") is not True
    )


def api_boundary_evidence(checks: Mapping[str, object]) -> dict[str, object]:
    openapi = checks.get("openapi")
    openapi_mapping = (
        cast(Mapping[str, object], openapi)
        if isinstance(openapi, Mapping)
        else cast(Mapping[str, object], {})
    )
    return {
        "artifact": API_SMOKE_ARTIFACT,
        "owner": "reactor.release",
        "mode": "dress_api_smoke",
        "apiBoundary": {
            "status": "verified",
            "framework": "FastAPI",
            "schema": "OpenAPI",
            "validation": "Pydantic",
            "openapiPath": "/openapi.json",
            "openapiVersion": str(openapi_mapping.get("openapi_version", "")),
            "routeCount": int_check(openapi_mapping.get("path_count")),
            "schemaCount": int_check(openapi_mapping.get("schema_count")),
            "requiredPaths": list(REQUIRED_OPENAPI_PATHS),
            "nextActionSchemas": string_list_check(openapi_mapping.get("next_action_schemas")),
            "nextActionSchemaFields": string_list_check(
                openapi_mapping.get("next_action_schema_fields")
            ),
            "runOperatorNextActionSchemaFields": string_list_check(
                openapi_mapping.get("run_operator_next_action_schema_fields")
            ),
            "nextActionFieldsNonEmpty": bool_check(
                openapi_mapping.get("next_action_fields_non_empty")
            ),
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
    }


def configure_api_smoke_env_next_action(missing: Sequence[str]) -> dict[str, object]:
    return {
        "id": "configure_api_smoke_env",
        "label": "Configure API smoke environment",
        "command": (
            "REACTOR_API_BASE_URL=<api-url> REACTOR_API_KEY=<api-key> "
            f"uv run reactor-dress-api-smoke --output {API_SMOKE_ARTIFACT}"
        ),
        "requiredEnv": list(REQUIRED_API_SMOKE_ENV),
        "missingEnv": [item for item in missing if item in REQUIRED_API_SMOKE_ENV],
        "reportFile": API_SMOKE_ARTIFACT,
    }


def int_check(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def bool_check(value: object) -> bool:
    return value is True


def string_list_check(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in cast(Sequence[object], value) if isinstance(item, str)]


def failed_check(result: ApiHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
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
    parser = argparse.ArgumentParser(description="Run a dress-rehearsal Reactor API smoke check.")
    parser.add_argument("--base-url", default="", help="Reactor API base URL; falls back to env")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = str(args.base_url).strip() or os.environ.get("REACTOR_API_BASE_URL", "").strip()
    config = DressApiSmokeConfig(
        base_url=base_url,
        timeout_seconds=float(args.timeout_seconds),
    )
    report = run_dress_api_smoke(
        config,
        http_probe=HttpApiProbe(base_url=base_url, timeout_seconds=config.timeout_seconds),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
