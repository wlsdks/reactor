from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import principal_from_headers
from reactor.api.schemas.rag_ingestion_policy import (
    RagIngestionPolicyResponse,
    RagIngestionPolicyStateResponse,
    UpdateRagIngestionPolicyRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.rag.ingestion_policy import (
    RagIngestionPolicy,
    RagIngestionPolicyProvider,
    RagIngestionPolicyStore,
    epoch_millis,
)

router = APIRouter(tags=["rag-ingestion-policy"])


@router.get(
    "/api/rag-ingestion/policy",
    response_model=RagIngestionPolicyStateResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/rag-ingestion/policy",
    response_model=RagIngestionPolicyStateResponse,
    response_model_by_alias=True,
)
async def get_rag_ingestion_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RagIngestionPolicyStateResponse | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    store = require_rag_ingestion_policy_store(request)
    if isinstance(store, JSONResponse):
        return store
    provider = require_rag_ingestion_policy_provider(request)
    if isinstance(provider, JSONResponse):
        return provider
    effective = await provider.current()
    stored = await store.get_or_none()
    settings = get_container(request).settings
    return RagIngestionPolicyStateResponse(
        configEnabled=settings.rag_ingestion_enabled,
        dynamicEnabled=settings.rag_ingestion_dynamic_enabled,
        effective=policy_response(effective),
        stored=policy_response(stored) if stored is not None else None,
    )


@router.put(
    "/api/rag-ingestion/policy",
    response_model=RagIngestionPolicyResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/rag-ingestion/policy",
    response_model=RagIngestionPolicyResponse,
    response_model_by_alias=True,
)
async def update_rag_ingestion_policy(
    request: Request,
    body: UpdateRagIngestionPolicyRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RagIngestionPolicyResponse | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    validation_error = validate_blocked_patterns(body.blockedPatterns)
    if validation_error is not None:
        return validation_error
    store = require_rag_ingestion_policy_store(request)
    if isinstance(store, JSONResponse):
        return store
    saved = await store.save(
        RagIngestionPolicy(
            enabled=body.enabled,
            require_review=body.requireReview,
            allowed_channels=tuple(body.allowedChannels),
            min_query_chars=body.minQueryChars,
            min_response_chars=body.minResponseChars,
            blocked_patterns=tuple(body.blockedPatterns),
        ),
        actor=current_actor(principal),
    )
    provider = require_rag_ingestion_policy_provider(request)
    if isinstance(provider, JSONResponse):
        return provider
    provider.invalidate()
    await record_policy_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.UPDATE,
        detail=(
            f"enabled={saved.enabled}, requireReview={saved.require_review}, "
            f"allowedChannels={len(saved.allowed_channels)}"
        ),
    )
    return policy_response(saved)


@router.delete(
    "/api/rag-ingestion/policy",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/v1/rag-ingestion/policy",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_rag_ingestion_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> Response | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    store = require_rag_ingestion_policy_store(request)
    if isinstance(store, JSONResponse):
        return store
    await store.delete()
    provider = require_rag_ingestion_policy_provider(request)
    if isinstance(provider, JSONResponse):
        return provider
    provider.invalidate()
    await record_policy_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.DELETE,
        detail="reset_to_config_defaults=true",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_admin(principal: AuthPrincipal) -> JSONResponse | None:
    if principal.is_any_admin():
        return None
    return legacy_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="관리자 권한이 필요합니다",
    )


def require_rag_ingestion_policy_store(
    request: Request,
) -> RagIngestionPolicyStore | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "rag_ingestion_policy_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        settings_accessor = getattr(container, "runtime_settings_store", None)
        settings_store = settings_accessor() if settings_accessor is not None else None
        if settings_store is not None:
            store = RagIngestionPolicyStore(settings_store)
    if store is None:
        return legacy_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="RagIngestionPolicyStore 미등록 — DB 미구성",
        )
    return cast(RagIngestionPolicyStore, store)


def require_rag_ingestion_policy_provider(
    request: Request,
) -> RagIngestionPolicyProvider | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "rag_ingestion_policy_provider", None)
    provider = accessor() if accessor is not None else None
    if provider is not None:
        return cast(RagIngestionPolicyProvider, provider)
    store = require_rag_ingestion_policy_store(request)
    if isinstance(store, JSONResponse):
        return store
    provider = getattr(request.app.state, "_rag_ingestion_policy_provider", None)
    if provider is None:
        provider = RagIngestionPolicyProvider(container.settings, store)
        request.app.state._rag_ingestion_policy_provider = provider
    return cast(RagIngestionPolicyProvider, provider)


def validate_blocked_patterns(patterns: set[str]) -> JSONResponse | None:
    for pattern in patterns:
        if len(pattern) > 500:
            return legacy_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error="각 blockedPattern은 500자 이하여야 합니다",
            )
        try:
            re.compile(pattern)
        except re.error:
            return legacy_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error=f"유효하지 않은 정규식 패턴: {pattern[:30]}...",
            )
    return None


async def record_policy_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    detail: str,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="rag_ingestion_policy",
            action=action,
            actor=current_actor(principal),
            resource_type="rag_ingestion_policy",
            resource_id="singleton",
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


def legacy_error_response(*, status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def policy_response(policy: RagIngestionPolicy) -> RagIngestionPolicyResponse:
    return RagIngestionPolicyResponse(
        enabled=policy.enabled,
        requireReview=policy.require_review,
        allowedChannels=policy.allowed_channels,
        minQueryChars=policy.min_query_chars,
        minResponseChars=policy.min_response_chars,
        blockedPatterns=policy.blocked_patterns,
        createdAt=epoch_millis(policy.created_at),
        updatedAt=epoch_millis(policy.updated_at),
    )
