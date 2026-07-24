from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class McpSecurityPolicyResponse(CamelModel):
    allowedServerNames: list[str]
    maxToolOutputLength: int
    createdAt: int
    updatedAt: int


class McpSecurityPolicyStateResponse(CamelModel):
    effective: McpSecurityPolicyResponse
    stored: McpSecurityPolicyResponse | None
    configDefault: McpSecurityPolicyResponse


class UpdateMcpSecurityPolicyRequest(CamelModel):
    allowedServerNames: set[str] = Field(default_factory=set, max_length=500)
    maxToolOutputLength: int = Field(default=50_000, ge=1_024, le=500_000)
