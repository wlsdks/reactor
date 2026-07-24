from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.api.auth import principal_from_headers
from reactor.api.schemas.personas import (
    CreatePersonaRequest,
    PersonaResponse,
    UpdatePersonaRequest,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.prompts.personas import PersonaRecord, epoch_millis

router = APIRouter(tags=["personas"])


class PersonaStore(Protocol):
    async def list(self) -> list[PersonaRecord]: ...

    async def list_active(self) -> list[PersonaRecord]: ...

    async def get(self, persona_id: str) -> PersonaRecord | None: ...

    async def get_default(self) -> PersonaRecord | None: ...

    async def save(self, record: PersonaRecord) -> PersonaRecord: ...

    async def update(
        self,
        persona_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        is_default: bool | None = None,
        description: str | None = None,
        response_guideline: str | None = None,
        welcome_message: str | None = None,
        icon: str | None = None,
        prompt_template_id: str | None = None,
        is_active: bool | None = None,
    ) -> PersonaRecord | None: ...

    async def delete(self, persona_id: str) -> None: ...


@router.get(
    "/api/personas",
    response_model=list[PersonaResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/personas",
    response_model=list[PersonaResponse],
    response_model_by_alias=True,
)
async def list_personas(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    activeOnly: bool = False,
) -> list[PersonaResponse] | JSONResponse:
    permission_error = require_persona_permission(principal, "persona:read")
    if permission_error is not None:
        return permission_error
    store = require_persona_store(request)
    if isinstance(store, JSONResponse):
        return store
    records = await store.list_active() if activeOnly else await store.list()
    return [persona_response(record) for record in records]


@router.get(
    "/api/personas/{persona_id}",
    response_model=PersonaResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/personas/{persona_id}",
    response_model=PersonaResponse,
    response_model_by_alias=True,
)
async def get_persona(
    request: Request,
    persona_id: str,
) -> PersonaResponse | JSONResponse:
    store = require_persona_store(request)
    if isinstance(store, JSONResponse):
        return store
    record = await store.get(persona_id)
    if record is None:
        return persona_not_found(persona_id)
    return persona_response(record)


@router.post(
    "/api/personas",
    response_model=PersonaResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/personas",
    response_model=PersonaResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_persona(
    request: Request,
    body: CreatePersonaRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> PersonaResponse | JSONResponse:
    permission_error = require_persona_permission(principal, "persona:write")
    if permission_error is not None:
        return permission_error
    store = require_persona_store(request)
    if isinstance(store, JSONResponse):
        return store
    saved = await store.save(
        PersonaRecord(
            name=body.name,
            system_prompt=body.systemPrompt,
            is_default=body.isDefault,
            description=body.description,
            response_guideline=body.responseGuideline,
            welcome_message=body.welcomeMessage,
            icon=body.icon,
            is_active=body.isActive,
            prompt_template_id=body.promptTemplateId,
        )
    )
    return persona_response(saved)


@router.put(
    "/api/personas/{persona_id}",
    response_model=PersonaResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/personas/{persona_id}",
    response_model=PersonaResponse,
    response_model_by_alias=True,
)
async def update_persona(
    request: Request,
    persona_id: str,
    body: UpdatePersonaRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> PersonaResponse | JSONResponse:
    permission_error = require_persona_permission(principal, "persona:write")
    if permission_error is not None:
        return permission_error
    store = require_persona_store(request)
    if isinstance(store, JSONResponse):
        return store
    updated = await store.update(
        persona_id,
        name=body.name,
        system_prompt=body.systemPrompt,
        is_default=body.isDefault,
        description=body.description,
        response_guideline=body.responseGuideline,
        welcome_message=body.welcomeMessage,
        icon=body.icon,
        prompt_template_id=body.promptTemplateId,
        is_active=body.isActive,
    )
    if updated is None:
        return persona_not_found(persona_id)
    return persona_response(updated)


@router.delete(
    "/api/personas/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/v1/personas/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_persona(
    request: Request,
    persona_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> Response | JSONResponse:
    permission_error = require_persona_permission(principal, "persona:write")
    if permission_error is not None:
        return permission_error
    store = require_persona_store(request)
    if isinstance(store, JSONResponse):
        return store
    await store.delete(persona_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_persona_permission(
    principal: AuthPrincipal,
    permission: str,
) -> JSONResponse | None:
    if principal.has_permission(permission):
        return None
    return legacy_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="관리자 권한이 필요합니다",
    )


def require_persona_store(request: Request) -> PersonaStore | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "persona_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return legacy_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="PersonaStore 미등록 — DB 미구성",
        )
    return cast(PersonaStore, store)


def persona_not_found(persona_id: str) -> JSONResponse:
    return legacy_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error=f"Persona not found: {persona_id}",
    )


def legacy_error_response(*, status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def persona_response(record: PersonaRecord) -> PersonaResponse:
    return PersonaResponse(
        id=record.id,
        name=record.name,
        systemPrompt=record.system_prompt,
        isDefault=record.is_default,
        description=record.description,
        responseGuideline=record.response_guideline,
        welcomeMessage=record.welcome_message,
        promptTemplateId=record.prompt_template_id,
        icon=record.icon,
        isActive=record.is_active,
        createdAt=epoch_millis(record.created_at),
        updatedAt=epoch_millis(record.updated_at),
    )
