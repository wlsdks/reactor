from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from reactor.api.auth import require_permission
from reactor.api.schemas.user_identities import (
    UserIdentityListResponse,
    UserIdentityResponse,
    UserIdentityUpsertRequest,
)
from reactor.auth.models import UserIdentityRecord
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer

router = APIRouter(tags=["user-identities"])


class UserIdentityStore(Protocol):
    async def upsert(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
        user_id: str,
        metadata: dict[str, object] | None = None,
    ) -> UserIdentityRecord: ...

    async def find_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> UserIdentityRecord | None: ...

    async def list_all(self, *, tenant_id: str) -> list[UserIdentityRecord]: ...

    async def list_for_user(self, *, tenant_id: str, user_id: str) -> list[UserIdentityRecord]: ...

    async def delete_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> bool: ...


@router.put(
    "/api/admin/user-identities",
    response_model=UserIdentityResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/user-identities",
    response_model=UserIdentityResponse,
    response_model_by_alias=True,
)
async def upsert_user_identity(
    request: Request,
    body: UserIdentityUpsertRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:write"))],
) -> UserIdentityResponse:
    record = await require_user_identity_store(request).upsert(
        tenant_id=principal.tenant_id,
        provider=body.provider.strip(),
        external_subject=body.external_subject.strip(),
        user_id=body.user_id.strip(),
        metadata=body.metadata,
    )
    return user_identity_response(record)


@router.get(
    "/api/admin/user-identities",
    response_model=UserIdentityListResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/user-identities",
    response_model=UserIdentityListResponse,
    response_model_by_alias=True,
)
async def list_user_identity_mappings(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:read"))],
) -> UserIdentityListResponse:
    records = await require_user_identity_store(request).list_all(tenant_id=principal.tenant_id)
    return UserIdentityListResponse(items=[user_identity_response(record) for record in records])


@router.get(
    "/api/admin/user-identities/by-external-subject",
    response_model=UserIdentityResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/user-identities/by-external-subject",
    response_model=UserIdentityResponse,
    response_model_by_alias=True,
)
async def get_user_identity_by_external_subject(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:read"))],
    provider: Annotated[str, Query(min_length=1)],
    external_subject: Annotated[str, Query(alias="externalSubject", min_length=1)],
) -> UserIdentityResponse:
    record = await require_user_identity_store(request).find_by_external_subject(
        tenant_id=principal.tenant_id,
        provider=provider.strip(),
        external_subject=external_subject.strip(),
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user identity mapping not found",
        )
    return user_identity_response(record)


@router.delete(
    "/api/admin/user-identities/by-external-subject",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/admin/user-identities/by-external-subject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_identity_by_external_subject(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:write"))],
    provider: Annotated[str, Query(min_length=1)],
    external_subject: Annotated[str, Query(alias="externalSubject", min_length=1)],
) -> Response:
    deleted = await require_user_identity_store(request).delete_by_external_subject(
        tenant_id=principal.tenant_id,
        provider=provider.strip(),
        external_subject=external_subject.strip(),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user identity mapping not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/admin/users/{user_id}/identities",
    response_model=UserIdentityListResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/users/{user_id}/identities",
    response_model=UserIdentityListResponse,
    response_model_by_alias=True,
)
async def list_user_identities(
    request: Request,
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:read"))],
) -> UserIdentityListResponse:
    records = await require_user_identity_store(request).list_for_user(
        tenant_id=principal.tenant_id,
        user_id=user_id,
    )
    return UserIdentityListResponse(items=[user_identity_response(record) for record in records])


def require_user_identity_store(request: Request) -> UserIdentityStore:
    container = get_container(request)
    accessor = getattr(container, "user_identity_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user identity persistence is not configured",
        )
    return cast(UserIdentityStore, store)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def user_identity_response(record: UserIdentityRecord) -> UserIdentityResponse:
    return UserIdentityResponse(
        id=record.id,
        tenantId=record.tenant_id,
        userId=record.user_id,
        provider=record.provider,
        externalSubject=record.external_subject,
        metadata=dict(record.metadata),
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )
