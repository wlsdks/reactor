from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KeyValueRequest(BaseModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class UserMemoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    facts: dict[str, str]
    preferences: dict[str, str]
    recent_topics: list[str] = Field(alias="recentTopics")
    updated_at: str = Field(alias="updatedAt")


class UserMemoryUpdateResponse(BaseModel):
    updated: bool
