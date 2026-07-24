from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AgentSpecResponse(CamelModel):
    id: str
    name: str
    description: str
    toolNames: tuple[str, ...]
    keywords: tuple[str, ...]
    systemPromptPreview: str | None
    hasSystemPrompt: bool
    mode: str
    independentExecution: bool
    enabled: bool
    createdAt: str
    updatedAt: str


class CreateAgentSpecRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    toolNames: tuple[str, ...] | None = None
    keywords: tuple[str, ...] | None = None
    systemPrompt: str | None = None
    mode: str | None = None
    independentExecution: bool | None = True
    enabled: bool | None = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name은 필수입니다")
        return value


class UpdateAgentSpecRequest(CamelModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    toolNames: tuple[str, ...] | None = None
    keywords: tuple[str, ...] | None = None
    systemPrompt: str | None = None
    mode: str | None = None
    independentExecution: bool | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name은 필수입니다")
        return value


class AgentSpecSystemPromptResponse(CamelModel):
    systemPrompt: str | None
