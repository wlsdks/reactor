from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from reactor.kernel.ids import new_id


class AgentSpecMode(StrEnum):
    REACT = "REACT"
    STANDARD = "STANDARD"
    PLAN_EXECUTE = "PLAN_EXECUTE"


@dataclass(frozen=True)
class AgentSpecRecord:
    id: str = field(default_factory=lambda: new_id("agent_spec"))
    name: str = ""
    description: str = ""
    tool_names: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    system_prompt: str | None = None
    mode: AgentSpecMode = AgentSpecMode.REACT
    independent_execution: bool = True
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if len(self.name) > 255:
            raise ValueError("name must be at most 255 characters")

    def with_updates(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        tool_names: tuple[str, ...] | None = None,
        keywords: tuple[str, ...] | None = None,
        system_prompt: str | None = None,
        mode: AgentSpecMode | None = None,
        independent_execution: bool | None = None,
        enabled: bool | None = None,
    ) -> AgentSpecRecord:
        return replace(
            self,
            name=self.name if name is None else name,
            description=self.description if description is None else description,
            tool_names=self.tool_names if tool_names is None else tool_names,
            keywords=self.keywords if keywords is None else keywords,
            system_prompt=self.system_prompt if system_prompt is None else system_prompt,
            mode=self.mode if mode is None else mode,
            independent_execution=(
                self.independent_execution
                if independent_execution is None
                else independent_execution
            ),
            enabled=self.enabled if enabled is None else enabled,
            updated_at=datetime.now(UTC),
        )


def parse_agent_spec_mode(value: str | None) -> AgentSpecMode | None:
    if value is None:
        return AgentSpecMode.REACT
    try:
        return AgentSpecMode(value)
    except ValueError:
        return None


def system_prompt_preview(system_prompt: str | None, *, max_chars: int = 120) -> str | None:
    prompt = system_prompt if system_prompt is not None and system_prompt.strip() else None
    if prompt is None:
        return None
    if len(prompt) <= max_chars:
        return prompt
    return prompt[:max_chars] + "\u2026"
