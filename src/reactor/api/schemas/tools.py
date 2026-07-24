from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCatalogUpsertRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4_000)
    risk_level: str = Field(alias="riskLevel", min_length=1)
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(alias="outputSchema")
    enabled: bool = True
    requires_approval: bool | None = Field(default=None, alias="requiresApproval")
    timeout_ms: int = Field(default=15_000, alias="timeoutMs", gt=0, le=300_000)


class ToolEnabledUpdateRequest(BaseModel):
    enabled: bool


class ToolCatalogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tenant_id: str = Field(alias="tenantId")
    namespace: str
    name: str
    qualified_name: str = Field(alias="qualifiedName")
    description: str
    risk_level: str = Field(alias="riskLevel")
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(alias="outputSchema")
    enabled: bool
    requires_approval: bool = Field(alias="requiresApproval")
    timeout_ms: int = Field(alias="timeoutMs")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ToolCatalogListResponse(BaseModel):
    total: int
    items: list[ToolCatalogResponse]


class UpdateToolPolicyRequest(BaseModel):
    enabled: bool = False
    write_tool_names: list[str] = Field(
        default_factory=list, alias="writeToolNames", max_length=500
    )
    deny_write_channels: list[str] = Field(
        default_factory=list,
        alias="denyWriteChannels",
        max_length=50,
    )
    allow_write_tool_names_in_deny_channels: list[str] = Field(
        default_factory=list,
        alias="allowWriteToolNamesInDenyChannels",
        max_length=500,
    )
    allow_write_tool_names_by_channel: dict[str, list[str]] = Field(
        default_factory=dict,
        alias="allowWriteToolNamesByChannel",
        max_length=200,
    )
    deny_write_message: str = Field(
        default="Error: This tool is not allowed in this channel",
        alias="denyWriteMessage",
        max_length=500,
    )


class ToolPolicyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool
    write_tool_names: list[str] = Field(alias="writeToolNames")
    deny_write_channels: list[str] = Field(alias="denyWriteChannels")
    allow_write_tool_names_in_deny_channels: list[str] = Field(
        alias="allowWriteToolNamesInDenyChannels"
    )
    allow_write_tool_names_by_channel: dict[str, list[str]] = Field(
        alias="allowWriteToolNamesByChannel"
    )
    deny_write_message: str = Field(alias="denyWriteMessage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ToolPolicyStateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_enabled: bool = Field(alias="configEnabled")
    dynamic_enabled: bool = Field(alias="dynamicEnabled")
    effective: ToolPolicyResponse
    stored: ToolPolicyResponse | None
