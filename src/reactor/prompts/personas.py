from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from reactor.kernel.ids import new_id


@dataclass(frozen=True)
class PersonaRecord:
    id: str = field(default_factory=lambda: new_id("persona"))
    name: str = ""
    system_prompt: str = ""
    is_default: bool = False
    description: str | None = None
    response_guideline: str | None = None
    welcome_message: str | None = None
    icon: str | None = None
    is_active: bool = True
    prompt_template_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if len(self.name) > 200:
            raise ValueError("name must be at most 200 characters")
        if not self.system_prompt.strip():
            raise ValueError("system_prompt is required")
        if len(self.system_prompt) > 50_000:
            raise ValueError("system_prompt must be at most 50000 characters")
        if self.description is not None and len(self.description) > 2_000:
            raise ValueError("description must be at most 2000 characters")
        if self.response_guideline is not None and len(self.response_guideline) > 10_000:
            raise ValueError("response_guideline must be at most 10000 characters")
        if self.welcome_message is not None and len(self.welcome_message) > 2_000:
            raise ValueError("welcome_message must be at most 2000 characters")
        if self.icon is not None and len(self.icon) > 20:
            raise ValueError("icon must be at most 20 characters")
        if self.prompt_template_id is not None and len(self.prompt_template_id) > 200:
            raise ValueError("prompt_template_id must be at most 200 characters")

    def with_updates(
        self,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        is_default: bool | None = None,
        description: str | None = None,
        response_guideline: str | None = None,
        welcome_message: str | None = None,
        icon: str | None = None,
        prompt_template_id: str | None = None,
        is_active: bool | None = None,
    ) -> PersonaRecord:
        updated = replace(
            self,
            name=self.name if name is None else name,
            system_prompt=self.system_prompt if system_prompt is None else system_prompt,
            is_default=self.is_default if is_default is None else is_default,
            description=resolve_nullable_field(description, self.description),
            response_guideline=resolve_nullable_field(
                response_guideline,
                self.response_guideline,
            ),
            welcome_message=resolve_nullable_field(welcome_message, self.welcome_message),
            icon=resolve_nullable_field(icon, self.icon),
            prompt_template_id=resolve_nullable_field(
                prompt_template_id,
                self.prompt_template_id,
            ),
            is_active=self.is_active if is_active is None else is_active,
            updated_at=datetime.now(UTC),
        )
        updated.validate()
        return updated


def resolve_nullable_field(new_value: str | None, existing: str | None) -> str | None:
    if new_value is None:
        return existing
    if new_value == "":
        return None
    return new_value


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)
