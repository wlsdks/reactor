from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InputGuardRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pattern: str = Field(min_length=1, max_length=5000)
    pattern_type: str = Field(default="regex", alias="patternType")
    action: str = "block"
    priority: int = Field(default=100, ge=0, le=10_000)
    category: str = Field(default="custom", max_length=32)
    description: str | None = Field(default=None, max_length=5000)
    enabled: bool = True


class InputGuardRuleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    pattern: str
    pattern_type: str = Field(alias="patternType")
    action: str
    priority: int
    category: str
    description: str | None
    enabled: bool
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class InputGuardRuleListResponse(BaseModel):
    rules: list[InputGuardRuleResponse]
    total: int


class InputGuardRuleDeleteResponse(BaseModel):
    deleted: bool
    id: str
