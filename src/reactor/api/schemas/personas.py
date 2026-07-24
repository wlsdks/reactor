from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PersonaResponse(CamelModel):
    id: str
    name: str
    systemPrompt: str
    isDefault: bool
    description: str | None
    responseGuideline: str | None
    welcomeMessage: str | None
    promptTemplateId: str | None
    icon: str | None
    isActive: bool
    createdAt: int
    updatedAt: int


class CreatePersonaRequest(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    systemPrompt: str = Field(min_length=1, max_length=50_000)
    isDefault: bool = False
    description: str | None = Field(default=None, max_length=2_000)
    responseGuideline: str | None = Field(default=None, max_length=10_000)
    welcomeMessage: str | None = Field(default=None, max_length=2_000)
    promptTemplateId: str | None = Field(default=None, max_length=200)
    icon: str | None = Field(default=None, max_length=20)
    isActive: bool = True

    @field_validator("name", "systemPrompt")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required field must not be blank")
        return value


class UpdatePersonaRequest(CamelModel):
    name: str | None = Field(default=None, max_length=200)
    systemPrompt: str | None = Field(default=None, max_length=50_000)
    isDefault: bool | None = None
    description: str | None = Field(default=None, max_length=2_000)
    responseGuideline: str | None = Field(default=None, max_length=10_000)
    welcomeMessage: str | None = Field(default=None, max_length=2_000)
    promptTemplateId: str | None = Field(default=None, max_length=200)
    icon: str | None = Field(default=None, max_length=20)
    isActive: bool | None = None
