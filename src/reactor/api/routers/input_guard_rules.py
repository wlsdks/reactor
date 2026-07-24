from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from reactor.api.auth import require_permission
from reactor.api.schemas.input_guard_rules import (
    InputGuardRuleDeleteResponse,
    InputGuardRuleListResponse,
    InputGuardRuleRequest,
    InputGuardRuleResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.guards.rules import (
    InputGuardRuleRecord,
    parse_pattern_type,
    parse_rule_action,
)
from reactor.persistence.input_guard_rule_store import SqlAlchemyInputGuardRuleStore

router = APIRouter(tags=["input-guard-rules"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_rule_store(request: Request) -> SqlAlchemyInputGuardRuleStore:
    store = get_container(request).input_guard_rule_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="input guard rule persistence is not configured",
        )
    return store


@router.get(
    "/api/admin/input-guard/rules",
    response_model=InputGuardRuleListResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/input-guard/rules",
    response_model=InputGuardRuleListResponse,
    response_model_by_alias=True,
)
async def list_rules(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> InputGuardRuleListResponse:
    rules = await require_rule_store(request).find_all(tenant_id=principal.tenant_id)
    return InputGuardRuleListResponse(
        rules=[rule_response(rule) for rule in rules], total=len(rules)
    )


@router.get(
    "/api/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
async def get_rule(
    request: Request,
    rule_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> InputGuardRuleResponse:
    rule = await require_rule_store(request).find_by_id(
        tenant_id=principal.tenant_id, rule_id=rule_id
    )
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="input guard rule not found"
        )
    return rule_response(rule)


@router.post(
    "/api/admin/input-guard/rules",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/input-guard/rules",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
async def create_rule(
    request: Request,
    body: InputGuardRuleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> InputGuardRuleResponse:
    rule = request_to_rule(body, tenant_id=principal.tenant_id)
    try:
        saved = await require_rule_store(request).save(rule)
    except ValueError as error:
        raise validation_error(error) from error
    return rule_response(saved)


@router.put(
    "/api/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleResponse,
    response_model_by_alias=True,
)
async def update_rule(
    request: Request,
    rule_id: str,
    body: InputGuardRuleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> InputGuardRuleResponse:
    rule = request_to_rule(body, tenant_id=principal.tenant_id, rule_id=rule_id)
    try:
        updated = await require_rule_store(request).update(
            tenant_id=principal.tenant_id,
            rule_id=rule_id,
            rule=rule,
        )
    except ValueError as error:
        raise validation_error(error) from error
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="input guard rule not found"
        )
    return rule_response(updated)


@router.delete(
    "/api/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleDeleteResponse,
)
@router.delete(
    "/v1/admin/input-guard/rules/{rule_id}",
    response_model=InputGuardRuleDeleteResponse,
)
async def delete_rule(
    request: Request,
    rule_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> InputGuardRuleDeleteResponse:
    deleted = await require_rule_store(request).delete(
        tenant_id=principal.tenant_id,
        rule_id=rule_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="input guard rule not found"
        )
    return InputGuardRuleDeleteResponse(deleted=True, id=rule_id)


def request_to_rule(
    body: InputGuardRuleRequest,
    *,
    tenant_id: str,
    rule_id: str | None = None,
) -> InputGuardRuleRecord:
    pattern_type = parse_pattern_type(body.pattern_type)
    if pattern_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patternType must be regex or keyword",
        )
    action = parse_rule_action(body.action)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be block, warn, or flag",
        )
    now = datetime.now(UTC)
    return InputGuardRuleRecord(
        id=rule_id or InputGuardRuleRecord().id,
        tenant_id=tenant_id,
        name=body.name,
        pattern=body.pattern,
        pattern_type=pattern_type,
        action=action,
        priority=body.priority,
        category=body.category or "custom",
        description=body.description,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )


def validation_error(error: ValueError) -> HTTPException:
    detail = "invalid regex pattern" if "regex" in str(error).lower() else str(error)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def rule_response(rule: InputGuardRuleRecord) -> InputGuardRuleResponse:
    return InputGuardRuleResponse(
        id=rule.id,
        name=rule.name,
        pattern=rule.pattern,
        patternType=rule.pattern_type.value,
        action=rule.action.value,
        priority=rule.priority,
        category=rule.category,
        description=rule.description,
        enabled=rule.enabled,
        createdAt=rule.created_at.isoformat(),
        updatedAt=rule.updated_at.isoformat(),
    )
