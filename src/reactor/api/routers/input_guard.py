from __future__ import annotations

from datetime import datetime
from inspect import isawaitable
from time import perf_counter
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from reactor.api.auth import require_permission
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.guards.input import InputGuard
from reactor.runtime_settings.service import GLOBAL_TENANT_ID, RuntimeSettingUpdate

router = APIRouter(tags=["input-guard"])


class GuardStageResponse(BaseModel):
    name: str
    order: int
    enabled: bool
    class_name: str = Field(alias="className")
    runtime_override: str | None = Field(default=None, alias="runtimeOverride")


class GuardSettingsRequest(BaseModel):
    settings: dict[str, str]


class GuardSimulateRequest(BaseModel):
    input: str = Field(min_length=1, max_length=50_000)
    user_id: str | None = Field(default=None, alias="userId")
    channel: str = "web"
    session_id: str | None = Field(default=None, alias="sessionId")


class StageConfigUpdateRequest(BaseModel):
    config: dict[str, str]


class PipelineReorderRequest(BaseModel):
    order: list[str] = Field(min_length=1)


INPUT_GUARD_STAGES = (
    GuardStageResponse(
        name="InputValidation",
        order=0,
        enabled=True,
        className="InputGuard",
    ),
    GuardStageResponse(
        name="InjectionDetection",
        order=1,
        enabled=True,
        className="InputGuard",
    ),
)

STAGE_CONFIG_SCHEMA: dict[str, dict[str, dict[str, Any]]] = {
    "InputValidation": {
        "maxLength": {
            "default": "10000",
            "type": "int",
            "description": "Maximum input characters",
            "restartRequired": True,
        },
        "minLength": {
            "default": "1",
            "type": "int",
            "description": "Minimum input characters",
            "restartRequired": True,
        },
    },
    "InjectionDetection": {
        "sensitivityLevel": {
            "default": "medium",
            "type": "enum(low|medium|high)",
            "description": "Prompt injection detection sensitivity",
            "restartRequired": True,
        }
    },
}


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.get(
    "/api/admin/input-guard/pipeline",
    response_model=list[GuardStageResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/input-guard/pipeline",
    response_model=list[GuardStageResponse],
    response_model_by_alias=True,
)
async def pipeline(
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> list[GuardStageResponse]:
    return list(INPUT_GUARD_STAGES)


@router.put("/api/admin/input-guard/settings")
@router.put("/v1/admin/input-guard/settings")
async def update_settings(
    request: Request,
    body: GuardSettingsRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> dict[str, object]:
    store = require_runtime_settings_store(request)
    updated = 0
    for key, value in body.settings.items():
        if not key.startswith("guard."):
            continue
        await store.set(
            RuntimeSettingUpdate(
                tenant_id=GLOBAL_TENANT_ID,
                key=key,
                value=value,
                category="guard",
                updated_by=principal.user_id,
            )
        )
        updated += 1
    return {"updated": updated, "note": "Some changes require service restart."}


@router.post("/api/admin/input-guard/simulate")
@router.post("/v1/admin/input-guard/simulate")
async def simulate(
    request: Request,
    body: GuardSimulateRequest,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> dict[str, object]:
    started = perf_counter()
    runtime_store = get_container(request).runtime_settings_store()
    evaluation = await InputGuard(runtime_settings_store=runtime_store).evaluate_async(
        body.input,
        tenant_id=GLOBAL_TENANT_ID,
    )
    duration_ms = int((perf_counter() - started) * 1000)
    if not evaluation.passed:
        stage_results = [
            stage_result(
                result.stage,
                index,
                result.passed,
                "allow" if result.passed else "block",
                duration_ms=duration_ms if not result.passed else 0,
                reason=result.reason,
                category=result.category,
            )
            for index, result in enumerate(evaluation.stage_results)
        ]
        return {
            "passed": False,
            "totalDurationMs": duration_ms,
            "finalAction": "block",
            "blockingStage": evaluation.blocking_stage,
            "stageResults": stage_results,
        }
    return {
        "passed": True,
        "totalDurationMs": duration_ms,
        "finalAction": "allow",
        "blockingStage": None,
        "stageResults": [
            stage_result(
                result.stage,
                index,
                True,
                "allow",
                duration_ms=duration_ms if index == len(evaluation.stage_results) - 1 else 0,
            )
            for index, result in enumerate(evaluation.stage_results)
        ],
    }


@router.get("/api/admin/input-guard/stats")
@router.get("/v1/admin/input-guard/stats")
async def stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
    hours: int = 24,
    tenantId: str | None = None,
) -> dict[str, object]:
    del tenantId
    period_hours = max(1, min(hours, 168))
    query = input_guard_stats_query(request)
    if query is None:
        return empty_stats_response(period_hours)
    result = await maybe_await(
        query.get_stats(period_hours=period_hours, tenant_id=principal.tenant_id)
    )
    return cast(dict[str, object], result)


@router.get("/api/admin/input-guard/audits")
@router.get("/v1/admin/input-guard/audits")
async def list_audits(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
    limit: int = Query(default=200),
    action: str | None = None,
) -> dict[str, object]:
    query = input_guard_stats_query(request)
    if query is None or not hasattr(query, "list_audits"):
        return {"audits": [], "total": 0}
    rows = await maybe_await(
        query.list_audits(
            limit=max(1, min(limit, 500)),
            tenant_id=principal.tenant_id,
            action=action,
        )
    )
    audits = [input_guard_audit_response(cast(dict[str, object], row)) for row in rows]
    return {"audits": audits, "total": len(audits)}


@router.get("/api/admin/input-guard/stages/{stage_name}/config")
@router.get("/v1/admin/input-guard/stages/{stage_name}/config")
async def get_stage_config(
    stage_name: str,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> dict[str, object]:
    stage = find_stage(stage_name)
    schema = STAGE_CONFIG_SCHEMA.get(stage_name, {})
    return {
        "stageName": stage_name,
        "className": stage.class_name,
        "enabled": stage.enabled,
        "order": stage.order,
        "config": {
            key: {
                "value": spec["default"],
                "default": spec["default"],
                "overridden": False,
                "type": spec["type"],
                "description": spec["description"],
                "restartRequired": spec["restartRequired"],
            }
            for key, spec in schema.items()
        },
        "note": None if schema else "This stage has no exposed tunable parameters.",
    }


@router.put("/api/admin/input-guard/stages/{stage_name}/config")
@router.put("/v1/admin/input-guard/stages/{stage_name}/config")
async def update_stage_config(
    request: Request,
    stage_name: str,
    body: StageConfigUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> dict[str, object]:
    find_stage(stage_name)
    schema = STAGE_CONFIG_SCHEMA.get(stage_name, {})
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{stage_name} has no exposed tunable parameters",
        )
    unknown = set(body.config) - set(schema)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown config keys: {sorted(unknown)}",
        )
    store = require_runtime_settings_store(request)
    for key, value in body.config.items():
        await store.set(
            RuntimeSettingUpdate(
                tenant_id=GLOBAL_TENANT_ID,
                key=f"guard.stage.{stage_name}.{key}",
                value=value,
                category="guard",
                updated_by=principal.user_id,
            )
        )
    restart_required = [
        key for key in body.config if bool(schema[key].get("restartRequired", False))
    ]
    return {
        "stageName": stage_name,
        "updated": len(body.config),
        "restartRequired": restart_required,
        "note": (
            "Changes apply immediately."
            if not restart_required
            else f"Restart required for: {restart_required}"
        ),
    }


@router.put("/api/admin/input-guard/pipeline/reorder")
@router.put("/v1/admin/input-guard/pipeline/reorder")
async def reorder_pipeline(
    request: Request,
    body: PipelineReorderRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> dict[str, object]:
    known = {stage.name for stage in INPUT_GUARD_STAGES}
    unknown = set(body.order) - known
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown stages: {sorted(unknown)}",
        )
    store = require_runtime_settings_store(request)
    for index, stage_name in enumerate(body.order):
        await store.set(
            RuntimeSettingUpdate(
                tenant_id=GLOBAL_TENANT_ID,
                key=f"guard.stage.{stage_name}.order",
                value=str(index),
                category="guard",
                updated_by=principal.user_id,
            )
        )
    return {"order": body.order, "note": "Pipeline order applies after service restart."}


def require_runtime_settings_store(request: Request):
    store = get_container(request).runtime_settings_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runtime settings persistence is not configured",
        )
    return store


def input_guard_stats_query(request: Request):
    accessor = getattr(get_container(request), "input_guard_stats_query", None)
    return accessor() if accessor is not None else None


def empty_stats_response(period_hours: int) -> dict[str, object]:
    return {
        "periodHours": period_hours,
        "totalRequests": 0,
        "totalAllowed": 0,
        "totalRejected": 0,
        "totalErrors": 0,
        "blockRate": 0.0,
        "byStage": [],
    }


def input_guard_audit_response(row: dict[str, object]) -> dict[str, object]:
    event_id = str(row.get("id") or "")
    user_id = text_value(row.get("user_id"))
    channel = text_value(row.get("channel"))
    stage = text_value(row.get("stage")) or "InputGuard"
    reason_class = text_value(row.get("reason_class"))
    reason_detail = text_value(row.get("reason_detail"))
    reason = ":".join(part for part in [reason_class, reason_detail] if part)
    response_id = (
        f"guard_evt_{event_id}" if event_id and not event_id.startswith("guard_evt_") else event_id
    )
    return {
        "id": response_id,
        "timestamp": timestamp_text(row.get("time")),
        "category": text_value(row.get("category")) or stage,
        "action": text_value(row.get("action")) or "allowed",
        "actor": f"user:{user_id}" if user_id else "system:input_guard",
        "resourceType": channel,
        "resourceId": user_id,
        "detail": f"stage={stage}" + (f", reason={reason}" if reason else ""),
    }


def timestamp_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def text_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


async def maybe_await[T](value: T) -> T:
    if isawaitable(value):
        return cast(T, await value)
    return value


def find_stage(stage_name: str) -> GuardStageResponse:
    for stage in INPUT_GUARD_STAGES:
        if stage.name == stage_name:
            return stage
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="guard stage not found")


def stage_result(
    stage: str,
    order: int,
    passed: bool,
    action: str,
    *,
    duration_ms: int,
    reason: str | None = None,
    category: str | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "order": order,
        "passed": passed,
        "action": action,
        "durationMs": duration_ms,
        "reason": reason,
        "category": category,
    }
