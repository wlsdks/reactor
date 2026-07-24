from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateOutputGuardRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pattern: str = Field(min_length=1, max_length=5000)
    action: str = "MASK"
    replacement: str = Field(default="[REDACTED]", max_length=256)
    priority: int = Field(default=100, ge=1, le=10_000)
    enabled: bool = True


class UpdateOutputGuardRuleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    pattern: str | None = Field(default=None, max_length=5000)
    action: str | None = None
    replacement: str | None = Field(default=None, max_length=256)
    priority: int | None = Field(default=None, ge=1, le=10_000)
    enabled: bool | None = None


class OutputGuardRuleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    pattern: str
    action: str
    replacement: str
    priority: int
    enabled: bool
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class OutputGuardRuleAuditResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    rule_id: str | None = Field(alias="ruleId")
    action: str
    actor: str
    detail: str | None
    created_at: int = Field(alias="createdAt")


class OutputGuardSimulationRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    include_disabled: bool = Field(default=False, alias="includeDisabled")


class OutputGuardSimulationMatchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(alias="ruleId")
    rule_name: str = Field(alias="ruleName")
    action: str
    priority: int


class OutputGuardSimulationInvalidRuleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(alias="ruleId")
    rule_name: str = Field(alias="ruleName")
    reason: str


class OutputGuardSimulationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    original_content: str = Field(alias="originalContent")
    result_content: str = Field(alias="resultContent")
    blocked: bool
    modified: bool
    blocked_by_rule_id: str | None = Field(alias="blockedByRuleId")
    blocked_by_rule_name: str | None = Field(alias="blockedByRuleName")
    matched_rules: list[OutputGuardSimulationMatchResponse] = Field(alias="matchedRules")
    invalid_rules: list[OutputGuardSimulationInvalidRuleResponse] = Field(alias="invalidRules")
