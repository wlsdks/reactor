from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class PromptProfile:
    name: str
    system_policy: str
    graph_profile: str
    version: str

    def validate(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("system_policy", self.system_policy),
            ("graph_profile", self.graph_profile),
            ("version", self.version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class PromptRelease:
    profile: PromptProfile
    developer_policy: str = ""
    examples: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def validate(self) -> None:
        self.profile.validate()
        for example in self.examples or []:
            if not example.strip():
                raise ValueError("example prompt must not be blank")

    @property
    def content_hash(self) -> str:
        self.validate()
        payload = {
            "developer_policy": self.developer_policy,
            "examples": self.examples or [],
            "graph_profile": self.profile.graph_profile,
            "metadata": self.metadata or {},
            "name": self.profile.name,
            "system_policy": self.profile.system_policy,
            "version": self.profile.version,
        }
        digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        return f"sha256:{digest}"


@dataclass(frozen=True)
class PromptDriftReport:
    profile_name: str
    version: str
    expected_hash: str
    actual_hash: str

    @property
    def drifted(self) -> bool:
        return self.expected_hash != self.actual_hash

    @classmethod
    def from_expected_hash(
        cls,
        *,
        release: PromptRelease,
        expected_hash: str,
    ) -> PromptDriftReport:
        return cls(
            profile_name=release.profile.name,
            version=release.profile.version,
            expected_hash=expected_hash,
            actual_hash=release.content_hash,
        )


def prompt_cache_key(
    *,
    tenant_id: str,
    release: PromptRelease,
    model_provider: str,
    model: str,
) -> str:
    for field_name, value in (
        ("tenant_id", tenant_id),
        ("model_provider", model_provider),
        ("model", model),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} is required")
    release.validate()
    return (
        f"prompt:{tenant_id}:{release.profile.name}:{release.profile.graph_profile}:"
        f"{release.profile.version}:{model_provider}:{model}:{release.content_hash}"
    )


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ToolForcingMode(StrEnum):
    AUTO = "auto"
    NONE = "none"
    REQUIRED = "required"
    FORCE_ONE = "force_one"


@dataclass(frozen=True)
class ToolForcingPolicy:
    mode: ToolForcingMode = ToolForcingMode.AUTO
    forced_tool: str | None = None

    def validate(self) -> None:
        if self.mode == ToolForcingMode.FORCE_ONE:
            if self.forced_tool is None or not self.forced_tool.strip():
                raise ValueError("forced_tool is required when mode is force_one")
            return
        if self.forced_tool is not None:
            raise ValueError("forced_tool is only valid when mode is force_one")


@dataclass(frozen=True)
class ToolExposureDecision:
    active_tools: list[str]
    tool_choice: str | dict[str, str] | None


def resolve_tool_exposure(
    *,
    profile_tools: list[str],
    request_tools: list[str] | None,
    policy: ToolForcingPolicy | None,
) -> ToolExposureDecision:
    active_tool_set = list(request_tools if request_tools is not None else profile_tools)
    if policy is None:
        return ToolExposureDecision(active_tools=active_tool_set, tool_choice=None)

    policy.validate()
    if policy.mode == ToolForcingMode.NONE:
        return ToolExposureDecision(active_tools=[], tool_choice="none")
    if policy.mode == ToolForcingMode.AUTO:
        return ToolExposureDecision(active_tools=active_tool_set, tool_choice=None)
    if policy.mode == ToolForcingMode.REQUIRED:
        if not active_tool_set:
            raise ValueError("required tool forcing policy needs at least one active tool")
        return ToolExposureDecision(active_tools=active_tool_set, tool_choice="required")

    forced_tool = policy.forced_tool
    if forced_tool not in active_tool_set:
        raise ValueError("forced_tool must be in active tool set")
    return ToolExposureDecision(
        active_tools=[forced_tool],
        tool_choice={"type": "tool", "name": forced_tool},
    )
