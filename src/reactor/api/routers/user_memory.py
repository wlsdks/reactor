from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from reactor.api.auth import principal_from_headers
from reactor.api.schemas.user_memory import (
    KeyValueRequest,
    UserMemoryResponse,
    UserMemoryUpdateResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.memory.service import UserMemoryService, UserMemoryStoreProtocol

router = APIRouter(tags=["user-memory"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def memory_service(request: Request) -> UserMemoryService:
    store = get_container(request).memory_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user memory persistence is not configured",
        )
    return UserMemoryService(cast(UserMemoryStoreProtocol, store))


@router.get(
    "/api/user-memory/{user_id}",
    response_model=UserMemoryResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/user-memory/{user_id}",
    response_model=UserMemoryResponse,
    response_model_by_alias=True,
)
async def get_user_memory(
    request: Request,
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> UserMemoryResponse:
    enforce_self_memory_access(user_id, principal)
    memory = await memory_service(request).get(tenant_id=principal.tenant_id, user_id=user_id)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User memory not found: {user_id}",
        )
    return UserMemoryResponse(
        facts=dict(memory.facts),
        preferences=dict(memory.preferences),
        recentTopics=memory.recent_topics,
        updatedAt=memory.updated_at.isoformat(),
    )


@router.put(
    "/api/user-memory/{user_id}/facts",
    response_model=UserMemoryUpdateResponse,
)
@router.put(
    "/v1/user-memory/{user_id}/facts",
    response_model=UserMemoryUpdateResponse,
)
async def update_fact(
    request: Request,
    user_id: str,
    body: KeyValueRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> UserMemoryUpdateResponse:
    enforce_self_memory_access(user_id, principal)
    try:
        await memory_service(request).update_fact(
            tenant_id=principal.tenant_id,
            user_id=user_id,
            key=body.key,
            value=body.value,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return UserMemoryUpdateResponse(updated=True)


@router.put(
    "/api/user-memory/{user_id}/preferences",
    response_model=UserMemoryUpdateResponse,
)
@router.put(
    "/v1/user-memory/{user_id}/preferences",
    response_model=UserMemoryUpdateResponse,
)
async def update_preference(
    request: Request,
    user_id: str,
    body: KeyValueRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> UserMemoryUpdateResponse:
    enforce_self_memory_access(user_id, principal)
    try:
        await memory_service(request).update_preference(
            tenant_id=principal.tenant_id,
            user_id=user_id,
            key=body.key,
            value=body.value,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return UserMemoryUpdateResponse(updated=True)


@router.delete("/api/user-memory/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/user-memory/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_memory(
    request: Request,
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> Response:
    enforce_self_memory_access(user_id, principal)
    await memory_service(request).delete(tenant_id=principal.tenant_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def enforce_self_memory_access(user_id: str, principal: AuthPrincipal) -> None:
    if user_id.lower() == "anonymous" or principal.user_id.lower() == "anonymous":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if principal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
