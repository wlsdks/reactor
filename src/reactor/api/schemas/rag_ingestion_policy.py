from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class RagIngestionPolicyResponse(CamelModel):
    enabled: bool
    requireReview: bool
    allowedChannels: tuple[str, ...]
    minQueryChars: int
    minResponseChars: int
    blockedPatterns: tuple[str, ...]
    createdAt: int
    updatedAt: int


class RagIngestionPolicyStateResponse(CamelModel):
    configEnabled: bool
    dynamicEnabled: bool
    effective: RagIngestionPolicyResponse
    stored: RagIngestionPolicyResponse | None


class UpdateRagIngestionPolicyRequest(CamelModel):
    enabled: bool = False
    requireReview: bool = True
    allowedChannels: set[str] = Field(default_factory=set, max_length=300)
    minQueryChars: int = 10
    minResponseChars: int = 20
    blockedPatterns: set[str] = Field(default_factory=set, max_length=500)
