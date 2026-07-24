from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RuntimeSettingType = Literal["STRING", "BOOLEAN", "INT", "DOUBLE", "JSON"]


class RuntimeSettingUpdateRequest(BaseModel):
    value: str = Field(min_length=0)
    type: RuntimeSettingType = "STRING"
    category: str = Field(default="general", min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeSettingResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    key: str
    value: str
    type: RuntimeSettingType
    category: str
    description: str | None
    updated_by: str | None = Field(alias="updatedBy")
    updated_at: datetime = Field(alias="updatedAt")
    metadata: dict[str, Any]


class RuntimeSettingsEffectiveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    applied_keys: list[str] = Field(alias="appliedKeys")
    ignored_keys: list[str] = Field(alias="ignoredKeys")
    errors: dict[str, str]


class LangChainMiddlewarePiiRuleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    strategy: str
    apply_to_input: bool = Field(alias="applyToInput")
    apply_to_output: bool = Field(alias="applyToOutput")
    apply_to_tool_results: bool = Field(alias="applyToToolResults")
    apply_to_stream_output: bool = Field(alias="applyToStreamOutput")


class LangChainMiddlewarePolicyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_call_run_limit: int | None = Field(alias="modelCallRunLimit")
    tool_call_run_limit: int | None = Field(alias="toolCallRunLimit")
    model_retry_max_retries: int = Field(alias="modelRetryMaxRetries")
    tool_retry_max_retries: int = Field(alias="toolRetryMaxRetries")
    pii_rules: list[LangChainMiddlewarePiiRuleResponse] = Field(alias="piiRules")


class LangChainMiddlewarePolicyPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    policy: dict[str, Any] = Field(default_factory=dict)
    interrupt_on_tools: list[str] = Field(default_factory=list, alias="interruptOnTools")


class LangChainMiddlewareChainPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["applied"]
    count: int
    middleware: list[str]
    pii_rule_count: int = Field(alias="piiRuleCount")
    hitl_tool_count: int = Field(alias="hitlToolCount")
    fallback_model_count: int = Field(alias="fallbackModelCount")


class LangChainMiddlewarePolicyDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    key: str
    status: Literal["applied", "default", "ignored"]
    source: Literal["tenant_runtime_setting", "global_runtime_setting", "default"]
    setting_tenant_id: str | None = Field(alias="settingTenantId")
    reason: str | None = None
    policy: LangChainMiddlewarePolicyResponse | None = None
    middleware_chain: LangChainMiddlewareChainPreviewResponse | None = Field(
        default=None,
        alias="middlewareChain",
    )


class LangChainMiddlewarePolicyPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    key: str
    status: Literal["preview"]
    source: Literal["request"]
    reason: str | None = None
    policy: LangChainMiddlewarePolicyResponse
    middleware_chain: LangChainMiddlewareChainPreviewResponse = Field(alias="middlewareChain")


class ToolProfileBudgetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_tools: int | None = Field(alias="maxTools")
    allowed_risk_levels: list[str] | None = Field(alias="allowedRiskLevels")
    allowed_tools: list[str] | None = Field(alias="allowedTools")
    denied_tools: list[str] = Field(alias="deniedTools")


class ToolProfileBudgetDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    key: str
    status: Literal["applied", "default", "ignored"]
    source: Literal["tenant_runtime_setting", "global_runtime_setting", "default"]
    setting_tenant_id: str | None = Field(alias="settingTenantId")
    reason: str | None = None
    budget: ToolProfileBudgetResponse | None = None
    configured_tool_count: int = Field(default=0, alias="configuredToolCount")
    active_tool_count: int = Field(default=0, alias="activeToolCount")
    active_tools: list[str] = Field(default_factory=list, alias="activeTools")
    dropped_tool_count: int = Field(default=0, alias="droppedToolCount")
    dropped_tools: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]](),
        alias="droppedTools",
    )


class ToolProfileBudgetPreviewToolRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1)
    risk_level: str = Field(alias="riskLevel", min_length=1)


class ToolProfileBudgetPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    budget: dict[str, Any] = Field(default_factory=dict)
    configured_tools: list[ToolProfileBudgetPreviewToolRequest] = Field(
        default_factory=lambda: [],
        alias="configuredTools",
    )


class ToolProfileBudgetPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    key: str
    status: Literal["preview"]
    source: Literal["request"]
    reason: str | None = None
    budget: ToolProfileBudgetResponse
    configured_tool_count: int = Field(alias="configuredToolCount")
    active_tool_count: int = Field(alias="activeToolCount")
    active_tools: list[str] = Field(alias="activeTools")
    dropped_tool_count: int = Field(alias="droppedToolCount")
    dropped_tools: list[dict[str, Any]] = Field(alias="droppedTools")


class RuntimeSettingUpdateResponse(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    key: str
    value: str
    status: str
