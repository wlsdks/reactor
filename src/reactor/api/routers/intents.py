from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from reactor.api.auth import require_permission
from reactor.api.schemas.intents import (
    CreateIntentRequest,
    IntentResponse,
    UpdateIntentRequest,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.guards.intents import IntentDefinition, IntentRegistry

router = APIRouter(tags=["intents"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_intent_registry(request: Request) -> IntentRegistry:
    accessor = getattr(get_container(request), "intent_registry", None)
    registry = accessor() if accessor is not None else None
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="intent registry persistence is not configured",
        )
    return cast(IntentRegistry, registry)


@router.get(
    "/api/intents",
    response_model=list[IntentResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/intents",
    response_model=list[IntentResponse],
    response_model_by_alias=True,
)
async def list_intents(
    request: Request,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> list[IntentResponse]:
    intents = await require_intent_registry(request).list()
    return [intent_response(intent) for intent in intents]


@router.get(
    "/api/intents/{intent_name}",
    response_model=IntentResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/intents/{intent_name}",
    response_model=IntentResponse,
    response_model_by_alias=True,
)
async def get_intent(
    request: Request,
    intent_name: str,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:read"))],
) -> IntentResponse:
    intent = await require_intent_registry(request).get(intent_name)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent not found: {intent_name}",
        )
    return intent_response(intent)


@router.post(
    "/api/intents",
    response_model=IntentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/intents",
    response_model=IntentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_intent(
    request: Request,
    body: CreateIntentRequest,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> IntentResponse:
    registry = require_intent_registry(request)
    existing = await registry.get(body.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Intent '{body.name}' already exists",
        )
    saved = await registry.save(
        IntentDefinition(
            name=body.name,
            description=body.description,
            examples=tuple(body.examples),
            keywords=tuple(body.keywords),
            profile=body.profile,
            enabled=body.enabled,
        )
    )
    return intent_response(saved)


@router.put(
    "/api/intents/{intent_name}",
    response_model=IntentResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/intents/{intent_name}",
    response_model=IntentResponse,
    response_model_by_alias=True,
)
async def update_intent(
    request: Request,
    intent_name: str,
    body: UpdateIntentRequest,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> IntentResponse:
    registry = require_intent_registry(request)
    existing = await registry.get(intent_name)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent not found: {intent_name}",
        )
    saved = await registry.save(
        existing.with_updates(
            description=body.description,
            examples=None if body.examples is None else tuple(body.examples),
            keywords=None if body.keywords is None else tuple(body.keywords),
            profile=body.profile,
            enabled=body.enabled,
        )
    )
    return intent_response(saved)


@router.delete("/api/intents/{intent_name}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/intents/{intent_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_intent(
    request: Request,
    intent_name: str,
    _: Annotated[AuthPrincipal, Depends(require_permission("guard:write"))],
) -> Response:
    await require_intent_registry(request).delete(intent_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def intent_response(intent: IntentDefinition) -> IntentResponse:
    return IntentResponse(
        name=intent.name,
        description=intent.description,
        examples=list(intent.examples),
        keywords=list(intent.keywords),
        profile=intent.profile,
        enabled=intent.enabled,
    )
