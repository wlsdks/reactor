from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DocumentAclRequest(CamelModel):
    visibility: Literal["public", "tenant", "private"]
    users: list[str] = Field(default_factory=list, max_length=1000)
    groups: list[str] = Field(default_factory=list, max_length=1000)

    @field_validator("users", "groups")
    @classmethod
    def normalize_non_empty_strings(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class AddDocumentRequest(CamelModel):
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] | None = Field(default=None, max_length=50)
    acl: DocumentAclRequest

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Document content is required")
        return value


class BatchAddDocumentRequest(CamelModel):
    documents: list[AddDocumentRequest] = Field(min_length=1, max_length=100)


class DocumentResponse(CamelModel):
    id: str
    content: str
    metadata: dict[str, Any]
    chunkCount: int = 1
    chunkIds: list[str] = Field(default_factory=list)


class BatchDocumentResponse(CamelModel):
    count: int
    totalChunks: int
    ids: list[str]


class SearchDocumentRequest(CamelModel):
    query: str = Field(min_length=1, max_length=10_000)
    topK: int | None = Field(default=5, ge=1, le=100)
    similarityThreshold: float | None = Field(default=0.0, ge=0.0)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search query is required")
        return value


class DeleteDocumentRequest(CamelModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class SearchResultResponse(CamelModel):
    id: str
    content: str
    metadata: dict[str, Any]
    score: float | None
