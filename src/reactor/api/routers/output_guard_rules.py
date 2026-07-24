from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.api.auth import require_permission
from reactor.api.schemas.output_guard_rules import (
    CreateOutputGuardRuleRequest,
    OutputGuardRuleAuditResponse,
    OutputGuardRuleResponse,
    OutputGuardSimulationInvalidRuleResponse,
    OutputGuardSimulationMatchResponse,
    OutputGuardSimulationRequest,
    OutputGuardSimulationResponse,
    UpdateOutputGuardRuleRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor, masked_admin_account_ref
from reactor.core.container import AppContainer
from reactor.guards.output_rules import (
    OutputGuardEvaluation,
    OutputGuardRuleAction,
    OutputGuardRuleAuditAction,
    OutputGuardRuleAuditRecord,
    OutputGuardRuleEvaluator,
    OutputGuardRuleRecord,
    parse_output_guard_action,
)
from reactor.persistence.output_guard_rule_store import (
    SqlAlchemyOutputGuardRuleAuditStore,
    SqlAlchemyOutputGuardRuleStore,
)

router = APIRouter(tags=["output-guard-rules"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def dynamic_rules_disabled_response(request: Request) -> JSONResponse | None:
    if not get_container(request).settings.output_guard_dynamic_rules_enabled:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Dynamic output guard rules are disabled"},
        )
    return None


def require_rule_store(request: Request) -> SqlAlchemyOutputGuardRuleStore:
    store = get_container(request).output_guard_rule_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="output guard rule persistence is not configured",
        )
    return store


def require_audit_store(request: Request) -> SqlAlchemyOutputGuardRuleAuditStore:
    store = get_container(request).output_guard_rule_audit_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="output guard rule audit persistence is not configured",
        )
    return store


@router.get(
    "/api/output-guard/rules",
    response_model=list[OutputGuardRuleResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/output-guard/rules",
    response_model=list[OutputGuardRuleResponse],
    response_model_by_alias=True,
)
async def list_rules(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> list[OutputGuardRuleResponse] | JSONResponse:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    rules = await require_rule_store(request).list(tenant_id=principal.tenant_id)
    return [rule_response(rule) for rule in rules]


@router.get(
    "/api/output-guard/rules/audits",
    response_model=list[OutputGuardRuleAuditResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/output-guard/rules/audits",
    response_model=list[OutputGuardRuleAuditResponse],
    response_model_by_alias=True,
)
async def list_audits(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
    limit: int = 100,
) -> list[OutputGuardRuleAuditResponse] | JSONResponse:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    logs = await require_audit_store(request).list(
        tenant_id=principal.tenant_id,
        limit=max(1, min(limit, 1000)),
    )
    return [audit_response(log) for log in logs]


@router.post(
    "/api/output-guard/rules",
    response_model=OutputGuardRuleResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/output-guard/rules",
    response_model=OutputGuardRuleResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    request: Request,
    body: CreateOutputGuardRuleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> OutputGuardRuleResponse | JSONResponse:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    rule = create_request_to_rule(body, tenant_id=principal.tenant_id)
    try:
        saved = await require_rule_store(request).save(rule)
    except ValueError as error:
        raise validation_error(error) from error
    await record_audit(
        request,
        tenant_id=principal.tenant_id,
        actor=current_actor(principal),
        action=OutputGuardRuleAuditAction.CREATE,
        rule_id=saved.id,
        detail=rule_detail(saved),
    )
    return rule_response(saved)


@router.put(
    "/api/output-guard/rules/{rule_id}",
    response_model=OutputGuardRuleResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/output-guard/rules/{rule_id}",
    response_model=OutputGuardRuleResponse,
    response_model_by_alias=True,
)
async def update_rule(
    request: Request,
    rule_id: str,
    body: UpdateOutputGuardRuleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> OutputGuardRuleResponse | JSONResponse:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    store = require_rule_store(request)
    existing = await store.find_by_id(tenant_id=principal.tenant_id, rule_id=rule_id)
    if existing is None:
        raise rule_not_found(rule_id)
    rule = update_request_to_rule(body, existing=existing)
    try:
        updated = await store.update(
            tenant_id=principal.tenant_id,
            rule_id=rule_id,
            rule=rule,
        )
    except ValueError as error:
        raise validation_error(error) from error
    if updated is None:
        raise rule_not_found(rule_id)
    await record_audit(
        request,
        tenant_id=principal.tenant_id,
        actor=current_actor(principal),
        action=OutputGuardRuleAuditAction.UPDATE,
        rule_id=updated.id,
        detail=rule_detail(updated),
    )
    return rule_response(updated)


@router.delete(
    "/api/output-guard/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/output-guard/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rule(
    request: Request,
    rule_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> Response:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    store = require_rule_store(request)
    existing = await store.find_by_id(tenant_id=principal.tenant_id, rule_id=rule_id)
    if existing is None:
        raise rule_not_found(rule_id)
    await store.delete(tenant_id=principal.tenant_id, rule_id=rule_id)
    await record_audit(
        request,
        tenant_id=principal.tenant_id,
        actor=current_actor(principal),
        action=OutputGuardRuleAuditAction.DELETE,
        rule_id=rule_id,
        detail=f"name={existing.name}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/output-guard/rules/simulate",
    response_model=OutputGuardSimulationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/output-guard/rules/simulate",
    response_model=OutputGuardSimulationResponse,
    response_model_by_alias=True,
)
async def simulate(
    request: Request,
    body: OutputGuardSimulationRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> OutputGuardSimulationResponse | JSONResponse:
    disabled = dynamic_rules_disabled_response(request)
    if disabled is not None:
        return disabled
    rules = await require_rule_store(request).list(
        tenant_id=principal.tenant_id,
        include_disabled=body.include_disabled,
    )
    evaluation = OutputGuardRuleEvaluator().evaluate(content=body.content, rules=rules)
    await record_audit(
        request,
        tenant_id=principal.tenant_id,
        actor=current_actor(principal),
        action=OutputGuardRuleAuditAction.SIMULATE,
        detail=(
            f"blocked={str(evaluation.blocked).lower()}, "
            f"matched={len(evaluation.matched_rules)}, "
            f"includeDisabled={str(body.include_disabled).lower()}"
        ),
    )
    return simulation_response(body.content, evaluation)


def create_request_to_rule(
    body: CreateOutputGuardRuleRequest, *, tenant_id: str
) -> OutputGuardRuleRecord:
    action = parse_output_guard_action(body.action)
    if action is None:
        raise invalid_action(body.action)
    now = datetime.now(UTC)
    return OutputGuardRuleRecord(
        tenant_id=tenant_id,
        name=body.name.strip(),
        pattern=body.pattern.strip(),
        action=action,
        replacement=body.replacement,
        priority=body.priority,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )


def update_request_to_rule(
    body: UpdateOutputGuardRuleRequest, *, existing: OutputGuardRuleRecord
) -> OutputGuardRuleRecord:
    action: OutputGuardRuleAction | None = None
    if body.action is not None:
        action = parse_output_guard_action(body.action)
        if action is None:
            raise invalid_action(body.action)
    return OutputGuardRuleRecord(
        id=existing.id,
        tenant_id=existing.tenant_id,
        name=(body.name.strip() if body.name is not None else existing.name),
        pattern=(body.pattern.strip() if body.pattern is not None else existing.pattern),
        action=action or existing.action,
        replacement=body.replacement if body.replacement is not None else existing.replacement,
        priority=body.priority if body.priority is not None else existing.priority,
        enabled=body.enabled if body.enabled is not None else existing.enabled,
        created_at=existing.created_at,
        updated_at=datetime.now(UTC),
    )


async def record_audit(
    request: Request,
    *,
    tenant_id: str,
    actor: str,
    action: OutputGuardRuleAuditAction,
    rule_id: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        audit_store = require_audit_store(request)
        await audit_store.save(
            OutputGuardRuleAuditRecord(
                tenant_id=tenant_id,
                rule_id=rule_id,
                action=action,
                actor=actor,
                detail=detail,
            )
        )
    except Exception:
        return


def validation_error(error: ValueError) -> HTTPException:
    detail = (
        "Invalid pattern: invalid regex pattern" if "regex" in str(error).lower() else str(error)
    )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def invalid_action(action: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid action: {action}",
    )


def rule_not_found(rule_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Output guard rule '{rule_id}' not found",
    )


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def rule_detail(rule: OutputGuardRuleRecord) -> str:
    return (
        f"name={rule.name}, action={rule.action.value}, "
        f"priority={rule.priority}, enabled={str(rule.enabled).lower()}"
    )


def rule_response(rule: OutputGuardRuleRecord) -> OutputGuardRuleResponse:
    return OutputGuardRuleResponse(
        id=rule.id,
        name=rule.name,
        pattern=rule.pattern,
        action=rule.action.value,
        replacement=rule.replacement,
        priority=rule.priority,
        enabled=rule.enabled,
        createdAt=epoch_millis(rule.created_at),
        updatedAt=epoch_millis(rule.updated_at),
    )


def audit_response(audit: OutputGuardRuleAuditRecord) -> OutputGuardRuleAuditResponse:
    return OutputGuardRuleAuditResponse(
        id=audit.id,
        ruleId=audit.rule_id,
        action=audit.action.value,
        actor=masked_admin_account_ref(audit.actor),
        detail=audit.detail,
        createdAt=epoch_millis(audit.created_at),
    )


def simulation_response(
    original_content: str,
    evaluation: OutputGuardEvaluation,
) -> OutputGuardSimulationResponse:
    blocked_by = evaluation.blocked_by
    return OutputGuardSimulationResponse(
        originalContent=original_content,
        resultContent=evaluation.content,
        blocked=evaluation.blocked,
        modified=evaluation.modified,
        blockedByRuleId=blocked_by.rule_id if blocked_by is not None else None,
        blockedByRuleName=blocked_by.rule_name if blocked_by is not None else None,
        matchedRules=[
            OutputGuardSimulationMatchResponse(
                ruleId=match.rule_id,
                ruleName=match.rule_name,
                action=match.action.value,
                priority=match.priority,
            )
            for match in evaluation.matched_rules
        ],
        invalidRules=[
            OutputGuardSimulationInvalidRuleResponse(
                ruleId=invalid.rule_id,
                ruleName=invalid.rule_name,
                reason=invalid.reason,
            )
            for invalid in evaluation.invalid_rules
        ],
    )
