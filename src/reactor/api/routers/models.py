from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from reactor.api.auth import require_any_admin
from reactor.api.schemas.models import AdminModelResponse, ModelInfoResponse, ModelsResponse
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.providers.model_registry import list_registered_models, list_registered_providers

router = APIRouter(tags=["models"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.get("/api/models", response_model=ModelsResponse, response_model_by_alias=True)
@router.get("/v1/models", response_model=ModelsResponse, response_model_by_alias=True)
async def list_models(request: Request) -> ModelsResponse:
    container = get_container(request)
    registered = await list_registered_models(
        container.settings,
        pricing_store_factory=getattr(container, "model_pricing_store", None),
    )
    providers = list_registered_providers(registered)
    default_provider = next(
        (provider.name for provider in providers if provider.is_default),
        container.settings.default_model_provider,
    )
    return ModelsResponse(
        models=[
            ModelInfoResponse(name=provider.name, isDefault=provider.is_default)
            for provider in providers
        ],
        defaultModel=default_provider,
    )


@router.get(
    "/api/admin/models",
    response_model=list[AdminModelResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/models",
    response_model=list[AdminModelResponse],
    response_model_by_alias=True,
)
async def list_admin_models(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[AdminModelResponse]:
    del principal
    container = get_container(request)
    registered = await list_registered_models(
        container.settings,
        pricing_store_factory=getattr(container, "model_pricing_store", None),
    )
    return [
        AdminModelResponse(
            name=model.name,
            provider=model.provider,
            inputPricePerMillionTokens=model.input_price_per_million_tokens,
            outputPricePerMillionTokens=model.output_price_per_million_tokens,
            isDefault=model.is_default,
        )
        for model in registered
    ]
