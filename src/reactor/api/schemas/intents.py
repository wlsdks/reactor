from __future__ import annotations

from pydantic import BaseModel, Field


class IntentResponse(BaseModel):
    name: str
    description: str
    examples: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    profile: str = "default"
    enabled: bool = True


class CreateIntentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=4_000)
    examples: list[str] = Field(default_factory=list, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    profile: str = Field(default="default", min_length=1, max_length=128)
    enabled: bool = True


class UpdateIntentRequest(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=4_000)
    examples: list[str] | None = Field(default=None, max_length=100)
    keywords: list[str] | None = Field(default=None, max_length=100)
    profile: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
