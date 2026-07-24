from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MediaUrlRequest(BaseModel):
    url: str = Field(min_length=1)
    mime_type: str = Field(alias="mimeType", min_length=1)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=50_000)
    model: str | None = None
    model_provider: str | None = Field(default=None, alias="modelProvider", min_length=1)
    system_prompt: str | None = Field(default=None, alias="systemPrompt", max_length=10_000)
    persona_id: str | None = Field(default=None, alias="personaId")
    prompt_template_id: str | None = Field(default=None, alias="promptTemplateId")
    user_id: str | None = Field(default=None, alias="userId")
    metadata: dict[str, Any] | None = Field(default=None, max_length=20)
    runtime: Literal["langgraph", "langchain_agent"] | None = None
    graph_profile: str | None = Field(
        default=None,
        alias="graphProfile",
        min_length=1,
        max_length=128,
    )
    checkpoint_ns: str | None = Field(
        default=None,
        alias="checkpointNs",
        min_length=1,
        max_length=128,
    )
    response_format: Literal["TEXT", "JSON"] | None = Field(default=None, alias="responseFormat")
    response_schema: str | None = Field(default=None, alias="responseSchema", max_length=10_000)
    fallback_models: list[str] = Field(default_factory=list, alias="fallbackModels", max_length=10)
    media_urls: list[MediaUrlRequest] | None = Field(default=None, alias="mediaUrls")


class ChatTokenUsage(BaseModel):
    input_tokens: int | None = Field(default=None, alias="inputTokens")
    output_tokens: int | None = Field(default=None, alias="outputTokens")
    total_tokens: int | None = Field(default=None, alias="totalTokens")


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content: str | None
    success: bool
    model: str | None = None
    tools_used: list[str] = Field(default_factory=list, alias="toolsUsed")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    error_message: str | None = Field(default=None, alias="errorMessage")
    error_code: str | None = Field(default=None, alias="errorCode")
    grounded: bool | None = None
    verified_source_count: int | None = Field(default=None, alias="verifiedSourceCount")
    block_reason: str | None = Field(default=None, alias="blockReason")
    token_usage: ChatTokenUsage | None = Field(default=None, alias="tokenUsage")
    metadata: dict[str, Any] = Field(default_factory=dict)
