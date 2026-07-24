from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    graph_profile: str = Field(alias="graphProfile", min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2_000)


class PromptVersionCreateRequest(BaseModel):
    version: str = Field(min_length=1, max_length=128)
    system_policy: str = Field(alias="systemPolicy", min_length=1)
    developer_policy: str = Field(default="", alias="developerPolicy")
    examples: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptReleaseCreateRequest(BaseModel):
    version_id: str = Field(alias="versionId", min_length=1, max_length=64)
    environment: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tenant_id: str = Field(alias="tenantId")
    name: str
    graph_profile: str = Field(alias="graphProfile")
    description: str | None
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class PromptVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    template_id: str = Field(alias="templateId")
    tenant_id: str = Field(alias="tenantId")
    version: str
    system_policy: str = Field(alias="systemPolicy")
    developer_policy: str = Field(alias="developerPolicy")
    examples: list[str]
    metadata: dict[str, Any]
    content_hash: str = Field(alias="contentHash")
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


class PromptReleaseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tenant_id: str = Field(alias="tenantId")
    template_id: str = Field(alias="templateId")
    version_id: str = Field(alias="versionId")
    environment: str
    released_by: str = Field(alias="releasedBy")
    released_at: datetime = Field(alias="releasedAt")
    metadata: dict[str, Any]


class PromptReleaseSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_name: str = Field(alias="profileName")
    graph_profile: str = Field(alias="graphProfile")
    version: str
    content_hash: str = Field(alias="contentHash")


class ReleasedPromptResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    template: PromptTemplateResponse
    version: PromptVersionResponse
    release: PromptReleaseResponse
    prompt_release: PromptReleaseSummary = Field(alias="promptRelease")


class LegacyPromptTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)


class LegacyPromptTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)


class LegacyPromptVersionCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    change_log: str = Field(default="", alias="changeLog", max_length=2_000)


class LegacyPromptVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    template_id: str = Field(alias="templateId")
    version: int
    content: str
    status: str
    change_log: str = Field(alias="changeLog")
    created_at: int = Field(alias="createdAt")


class LegacyPromptTemplateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class LegacyPromptTemplateDetailResponse(LegacyPromptTemplateResponse):
    active_version: LegacyPromptVersionResponse | None = Field(alias="activeVersion")
    versions: list[LegacyPromptVersionResponse]
