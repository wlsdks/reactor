from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from reactor.api.auth import principal_from_headers, require_permission
from reactor.api.schemas.prompt import (
    LegacyPromptTemplateCreateRequest,
    LegacyPromptTemplateDetailResponse,
    LegacyPromptTemplateResponse,
    LegacyPromptTemplateUpdateRequest,
    LegacyPromptVersionCreateRequest,
    LegacyPromptVersionResponse,
    PromptReleaseCreateRequest,
    PromptReleaseResponse,
    PromptReleaseSummary,
    PromptTemplateCreateRequest,
    PromptTemplateResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
    ReleasedPromptResponse,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.persistence.prompt_store import (
    PromptReleaseRecord,
    PromptTemplateRecord,
    PromptVersionRecord,
    ReleasedPromptRecord,
    legacy_change_log,
    legacy_status,
    legacy_version_number,
)
from reactor.prompts.profiles import PromptProfile, PromptRelease

router = APIRouter(tags=["prompts"])


class PromptStore(Protocol):
    async def list_templates(self, *, tenant_id: str) -> list[PromptTemplateRecord]: ...

    async def save_template(self, record: PromptTemplateRecord) -> PromptTemplateRecord: ...

    async def find_template_by_id(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> PromptTemplateRecord | None: ...

    async def update_template(
        self,
        *,
        tenant_id: str,
        template_id: str,
        name: str | None,
        description: str | None,
        updated_at: datetime,
    ) -> PromptTemplateRecord | None: ...

    async def delete_template(self, *, tenant_id: str, template_id: str) -> None: ...

    async def save_version(self, record: PromptVersionRecord) -> PromptVersionRecord: ...

    async def list_versions(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> list[PromptVersionRecord]: ...

    async def create_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        content: str,
        change_log: str,
        created_by: str,
        created_at: datetime,
        version_id: str,
    ) -> PromptVersionRecord | None: ...

    async def activate_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None: ...

    async def archive_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None: ...

    async def save_release(self, record: PromptReleaseRecord) -> PromptReleaseRecord: ...

    async def find_released(
        self,
        *,
        tenant_id: str,
        template_name: str,
        environment: str,
    ) -> ReleasedPromptRecord | None: ...


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_prompt_store(request: Request) -> PromptStore:
    store = get_container(request).prompt_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt persistence is not configured",
        )
    return cast(PromptStore, store)


@router.get(
    "/api/prompt-templates",
    response_model=list[LegacyPromptTemplateResponse],
    response_model_by_alias=True,
)
async def list_legacy_prompt_templates(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> list[LegacyPromptTemplateResponse]:
    records = await require_prompt_store(request).list_templates(tenant_id=principal.tenant_id)
    return [legacy_template_response(record) for record in records]


@router.post(
    "/api/prompt-templates",
    response_model=LegacyPromptTemplateResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_legacy_prompt_template(
    request: Request,
    body: LegacyPromptTemplateCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> LegacyPromptTemplateResponse:
    now = datetime.now(UTC)
    record = PromptTemplateRecord(
        id=prompt_id("prompt_template"),
        tenant_id=principal.tenant_id,
        name=body.name.strip(),
        graph_profile="legacy",
        description=body.description.strip(),
        created_by=current_actor(principal),
        created_at=now,
        updated_at=now,
    )
    saved = await require_prompt_store(request).save_template(record)
    return legacy_template_response(saved)


@router.get(
    "/api/prompt-templates/{template_id}",
    response_model=LegacyPromptTemplateDetailResponse,
    response_model_by_alias=True,
)
async def get_legacy_prompt_template(
    request: Request,
    template_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> LegacyPromptTemplateDetailResponse:
    store = require_prompt_store(request)
    template = await store.find_template_by_id(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt template not found"
        )
    versions = await store.list_versions(
        tenant_id=principal.tenant_id,
        template_id=template.id,
    )
    active = next(
        (version for version in versions if legacy_status(version) == "ACTIVE"),
        None,
    )
    return legacy_template_detail_response(template, versions, active)


@router.put(
    "/api/prompt-templates/{template_id}",
    response_model=LegacyPromptTemplateResponse,
    response_model_by_alias=True,
)
async def update_legacy_prompt_template(
    request: Request,
    template_id: str,
    body: LegacyPromptTemplateUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> LegacyPromptTemplateResponse:
    updated = await require_prompt_store(request).update_template(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
        name=body.name.strip() if body.name is not None else None,
        description=body.description.strip() if body.description is not None else None,
        updated_at=datetime.now(UTC),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt template not found"
        )
    return legacy_template_response(updated)


@router.delete(
    "/api/prompt-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_legacy_prompt_template(
    request: Request,
    template_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> Response:
    await require_prompt_store(request).delete_template(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/prompt-templates/{template_id}/versions",
    response_model=LegacyPromptVersionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_legacy_prompt_version(
    request: Request,
    template_id: str,
    body: LegacyPromptVersionCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> LegacyPromptVersionResponse:
    version = await require_prompt_store(request).create_legacy_version(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
        content=body.content.strip(),
        change_log=body.change_log.strip(),
        created_by=current_actor(principal),
        created_at=datetime.now(UTC),
        version_id=prompt_id("prompt_version"),
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt template not found"
        )
    return legacy_version_response(version)


@router.put(
    "/api/prompt-templates/{template_id}/versions/{version_id}/activate",
    response_model=LegacyPromptVersionResponse,
    response_model_by_alias=True,
)
async def activate_legacy_prompt_version(
    request: Request,
    template_id: str,
    version_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> LegacyPromptVersionResponse:
    version = await require_prompt_store(request).activate_legacy_version(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
        version_id=version_id.strip(),
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt version not found"
        )
    return legacy_version_response(version)


@router.put(
    "/api/prompt-templates/{template_id}/versions/{version_id}/archive",
    response_model=LegacyPromptVersionResponse,
    response_model_by_alias=True,
)
async def archive_legacy_prompt_version(
    request: Request,
    template_id: str,
    version_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> LegacyPromptVersionResponse:
    version = await require_prompt_store(request).archive_legacy_version(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
        version_id=version_id.strip(),
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt version not found"
        )
    return legacy_version_response(version)


@router.post(
    "/api/admin/prompts/templates",
    response_model=PromptTemplateResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/prompts/templates",
    response_model=PromptTemplateResponse,
    response_model_by_alias=True,
)
async def create_prompt_template(
    request: Request,
    body: PromptTemplateCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptTemplateResponse:
    now = datetime.now(UTC)
    record = PromptTemplateRecord(
        id=prompt_id("prompt_template"),
        tenant_id=principal.tenant_id,
        name=body.name.strip(),
        graph_profile=body.graph_profile.strip(),
        description=body.description.strip() if body.description is not None else None,
        created_by=current_actor(principal),
        created_at=now,
        updated_at=now,
    )
    saved = await require_prompt_store(request).save_template(record)
    return prompt_template_response(saved)


@router.post(
    "/api/admin/prompts/templates/{template_id}/versions",
    response_model=PromptVersionResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/prompts/templates/{template_id}/versions",
    response_model=PromptVersionResponse,
    response_model_by_alias=True,
)
async def create_prompt_version(
    request: Request,
    template_id: str,
    body: PromptVersionCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptVersionResponse:
    store = require_prompt_store(request)
    template = await store.find_template_by_id(
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt template not found"
        )
    prompt_release = PromptRelease(
        profile=PromptProfile(
            name=template.name,
            system_policy=body.system_policy,
            graph_profile=template.graph_profile,
            version=body.version,
        ),
        developer_policy=body.developer_policy,
        examples=body.examples,
        metadata=body.metadata,
    )
    record = PromptVersionRecord(
        id=prompt_id("prompt_version"),
        template_id=template_id.strip(),
        tenant_id=principal.tenant_id,
        version=body.version.strip(),
        system_policy=body.system_policy.strip(),
        developer_policy=body.developer_policy.strip(),
        examples=[example.strip() for example in body.examples],
        metadata=body.metadata,
        content_hash=prompt_release.content_hash,
        created_by=current_actor(principal),
        created_at=datetime.now(UTC),
    )
    saved = await store.save_version(record)
    return prompt_version_response(saved)


@router.post(
    "/api/admin/prompts/templates/{template_id}/releases",
    response_model=PromptReleaseResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/prompts/templates/{template_id}/releases",
    response_model=PromptReleaseResponse,
    response_model_by_alias=True,
)
async def release_prompt_version(
    request: Request,
    template_id: str,
    body: PromptReleaseCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptReleaseResponse:
    record = PromptReleaseRecord(
        id=prompt_id("prompt_release"),
        tenant_id=principal.tenant_id,
        template_id=template_id.strip(),
        version_id=body.version_id.strip(),
        environment=body.environment.strip(),
        released_by=current_actor(principal),
        released_at=datetime.now(UTC),
        metadata=body.metadata,
    )
    saved = await require_prompt_store(request).save_release(record)
    return prompt_release_response(saved)


@router.get(
    "/api/admin/prompts/{template_name}/releases/{environment}",
    response_model=ReleasedPromptResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/prompts/{template_name}/releases/{environment}",
    response_model=ReleasedPromptResponse,
    response_model_by_alias=True,
)
async def get_released_prompt(
    request: Request,
    template_name: str,
    environment: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
) -> ReleasedPromptResponse:
    released = await require_prompt_store(request).find_released(
        tenant_id=principal.tenant_id,
        template_name=template_name.strip(),
        environment=environment.strip(),
    )
    if released is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt release not found"
        )
    return released_prompt_response(released)


def legacy_template_response(record: PromptTemplateRecord) -> LegacyPromptTemplateResponse:
    return LegacyPromptTemplateResponse(
        id=record.id,
        name=record.name,
        description=record.description or "",
        createdAt=epoch_millis(record.created_at),
        updatedAt=epoch_millis(record.updated_at),
    )


def legacy_template_detail_response(
    template: PromptTemplateRecord,
    versions: list[PromptVersionRecord],
    active: PromptVersionRecord | None,
) -> LegacyPromptTemplateDetailResponse:
    return LegacyPromptTemplateDetailResponse(
        id=template.id,
        name=template.name,
        description=template.description or "",
        activeVersion=legacy_version_response(active) if active is not None else None,
        versions=[legacy_version_response(version) for version in versions],
        createdAt=epoch_millis(template.created_at),
        updatedAt=epoch_millis(template.updated_at),
    )


def legacy_version_response(record: PromptVersionRecord) -> LegacyPromptVersionResponse:
    return LegacyPromptVersionResponse(
        id=record.id,
        templateId=record.template_id,
        version=legacy_version_number(record),
        content=record.system_policy,
        status=legacy_status(record),
        changeLog=legacy_change_log(record),
        createdAt=epoch_millis(record.created_at),
    )


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def prompt_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def prompt_template_response(record: PromptTemplateRecord) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=record.id,
        tenantId=record.tenant_id,
        name=record.name,
        graphProfile=record.graph_profile,
        description=record.description,
        createdBy=record.created_by,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def prompt_version_response(record: PromptVersionRecord) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=record.id,
        templateId=record.template_id,
        tenantId=record.tenant_id,
        version=record.version,
        systemPolicy=record.system_policy,
        developerPolicy=record.developer_policy,
        examples=record.examples,
        metadata=record.metadata,
        contentHash=record.content_hash,
        createdBy=record.created_by,
        createdAt=record.created_at,
    )


def prompt_release_response(record: PromptReleaseRecord) -> PromptReleaseResponse:
    return PromptReleaseResponse(
        id=record.id,
        tenantId=record.tenant_id,
        templateId=record.template_id,
        versionId=record.version_id,
        environment=record.environment,
        releasedBy=record.released_by,
        releasedAt=record.released_at,
        metadata=record.metadata,
    )


def released_prompt_response(record: ReleasedPromptRecord) -> ReleasedPromptResponse:
    return ReleasedPromptResponse(
        template=prompt_template_response(record.template),
        version=prompt_version_response(record.version),
        release=prompt_release_response(record.release),
        promptRelease=PromptReleaseSummary(
            profileName=record.template.name,
            graphProfile=record.template.graph_profile,
            version=record.version.version,
            contentHash=record.version.content_hash,
        ),
    )
