from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from reactor.auth.rbac import UserRole


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    name: str
    password_hash: str
    role: UserRole = UserRole.USER
    tenant_id: str = "default"
    groups: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("email", self.email),
            ("name", self.name),
            ("password_hash", self.password_hash),
            ("tenant_id", self.tenant_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if "@" not in self.email:
            raise ValueError("email must contain @")
        for group in self.groups:
            if not group.strip():
                raise ValueError("groups must contain non-empty strings")


def normalize_groups(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("groups must be a sequence of strings")
    groups: list[str] = []
    seen: set[str] = set()
    for raw_group in cast(Sequence[object], value):
        if not isinstance(raw_group, str):
            raise ValueError("groups must contain strings")
        group = raw_group.strip()
        if not group or group in seen:
            continue
        groups.append(group)
        seen.add(group)
    return tuple(groups)


@dataclass(frozen=True)
class TokenRevocationRecord:
    token_id: str
    expires_at: datetime
    revoked_at: datetime

    def validate(self) -> None:
        if not self.token_id.strip():
            raise ValueError("token_id is required")


def empty_metadata() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class UserIdentityRecord:
    id: str
    tenant_id: str
    user_id: str
    provider: str
    external_subject: str
    metadata: dict[str, Any] = field(default_factory=empty_metadata)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("user_id", self.user_id),
            ("provider", self.provider),
            ("external_subject", self.external_subject),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
