from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from reactor.core.settings import Settings
from reactor.runtime_settings.service import (
    FALSE_VALUES,
    GLOBAL_TENANT_ID,
    TRUE_VALUES,
    RuntimeSettingRecord,
    RuntimeSettingsResolver,
)

SETTINGS_KEY_PREFIX = "settings."


def empty_errors() -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class RuntimeSettingsApplyResult:
    settings: Settings
    applied_keys: tuple[str, ...] = ()
    ignored_keys: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=empty_errors)


def apply_runtime_settings_to_settings(
    base_settings: Settings,
    resolver: RuntimeSettingsResolver,
    *,
    tenant_id: str = GLOBAL_TENANT_ID,
    key_prefix: str = SETTINGS_KEY_PREFIX,
) -> RuntimeSettingsApplyResult:
    updates: dict[str, object] = {}
    update_keys: dict[str, str] = {}
    ignored_keys: list[str] = []
    errors: dict[str, str] = {}

    for field_name in Settings.model_fields:
        key = f"{key_prefix}{field_name}"
        record = resolver.find(key, tenant_id=tenant_id)
        if record is None:
            continue
        try:
            updates[field_name] = runtime_setting_value(record)
            update_keys[field_name] = key
        except ValueError as error:
            ignored_keys.append(key)
            errors[key] = str(error)

    if not updates:
        return RuntimeSettingsApplyResult(
            settings=base_settings,
            ignored_keys=tuple(ignored_keys),
            errors=errors,
        )

    raw_settings: dict[str, Any] = base_settings.model_dump()
    raw_settings.update(updates)
    try:
        settings = Settings.model_validate(raw_settings)
    except ValueError as error:
        return RuntimeSettingsApplyResult(
            settings=base_settings,
            ignored_keys=tuple(sorted({*ignored_keys, *update_keys.values()})),
            errors={**errors, "__settings__": str(error)},
        )

    return RuntimeSettingsApplyResult(
        settings=settings,
        applied_keys=tuple(update_keys.values()),
        ignored_keys=tuple(ignored_keys),
        errors=errors,
    )


def runtime_setting_value(record: RuntimeSettingRecord) -> object:
    match record.value_type:
        case "BOOLEAN":
            normalized = record.value.strip().lower()
            if normalized in TRUE_VALUES:
                return True
            if normalized in FALSE_VALUES:
                return False
            raise ValueError(f"invalid BOOLEAN value for {record.key}")
        case "INT":
            try:
                return int(record.value)
            except ValueError as error:
                raise ValueError(f"invalid INT value for {record.key}") from error
        case "DOUBLE":
            try:
                return float(record.value)
            except ValueError as error:
                raise ValueError(f"invalid DOUBLE value for {record.key}") from error
        case "JSON":
            try:
                return json.loads(record.value)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON value for {record.key}") from error
        case "STRING":
            return record.value
    raise ValueError(f"unsupported runtime setting type: {record.value_type}")
