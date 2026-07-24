from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

GLOBAL_TENANT_ID = "global"
RuntimeSettingType = Literal["STRING", "BOOLEAN", "INT", "DOUBLE", "JSON"]
SUPPORTED_TYPES: set[str] = {"STRING", "BOOLEAN", "INT", "DOUBLE", "JSON"}
TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}


def dict_metadata() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class RuntimeSettingRecord:
    key: str
    value: str
    value_type: RuntimeSettingType = "STRING"
    category: str = "general"
    tenant_id: str = GLOBAL_TENANT_ID
    description: str | None = None
    updated_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, Any] = field(default_factory=dict_metadata)

    def validate(self) -> None:
        validate_key(self.key)
        validate_tenant_id(self.tenant_id)
        if self.value_type not in SUPPORTED_TYPES:
            raise ValueError(f"unsupported runtime setting type: {self.value_type}")
        if not self.category.strip():
            raise ValueError("category is required")


@dataclass(frozen=True)
class RuntimeSettingUpdate:
    key: str
    value: str
    value_type: RuntimeSettingType = "STRING"
    category: str = "general"
    tenant_id: str = GLOBAL_TENANT_ID
    description: str | None = None
    updated_by: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict_metadata)

    def validate(self) -> None:
        RuntimeSettingRecord(
            key=self.key,
            value=self.value,
            value_type=self.value_type,
            category=self.category,
            tenant_id=self.tenant_id,
            description=self.description,
            updated_by=self.updated_by,
            metadata=self.metadata,
        ).validate()


class RuntimeSettingsResolver:
    def __init__(self, settings: Iterable[RuntimeSettingRecord] = ()) -> None:
        self._settings = {(setting.tenant_id, setting.key): setting for setting in settings}
        for setting in self._settings.values():
            setting.validate()

    def find(self, key: str, *, tenant_id: str = GLOBAL_TENANT_ID) -> RuntimeSettingRecord | None:
        validate_key(key)
        validate_tenant_id(tenant_id)
        return self._settings.get((tenant_id, key)) or self._settings.get((GLOBAL_TENANT_ID, key))

    def get_string(
        self,
        key: str,
        default: str,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> str:
        setting = self.find(key, tenant_id=tenant_id)
        return setting.value if setting is not None else default

    def get_boolean(
        self,
        key: str,
        default: bool,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> bool:
        setting = self.find(key, tenant_id=tenant_id)
        if setting is None:
            return default
        normalized = setting.value.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        return default

    def get_int(self, key: str, default: int, *, tenant_id: str = GLOBAL_TENANT_ID) -> int:
        setting = self.find(key, tenant_id=tenant_id)
        if setting is None:
            return default
        try:
            return int(setting.value)
        except ValueError:
            return default

    def get_double(
        self,
        key: str,
        default: float,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> float:
        setting = self.find(key, tenant_id=tenant_id)
        if setting is None:
            return default
        try:
            return float(setting.value)
        except ValueError:
            return default


def validate_key(key: str) -> None:
    if not key.strip():
        raise ValueError("key is required")
    if any(character.isspace() for character in key):
        raise ValueError("key must not contain whitespace")


def validate_tenant_id(tenant_id: str) -> None:
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if any(character.isspace() for character in tenant_id):
        raise ValueError("tenant_id must not contain whitespace")
