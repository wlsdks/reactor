from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserIdentityUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId", min_length=1)
    provider: str = Field(min_length=1)
    external_subject: str = Field(alias="externalSubject", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserIdentityResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tenant_id: str = Field(alias="tenantId")
    user_id: str = Field(alias="userId")
    provider: str
    external_subject: str = Field(alias="externalSubject")
    metadata: dict[str, Any]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class UserIdentityListResponse(BaseModel):
    items: list[UserIdentityResponse]
