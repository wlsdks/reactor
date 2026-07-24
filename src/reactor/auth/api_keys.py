from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest

from reactor.auth.rbac import AuthPrincipal, UserRole, parse_groups, parse_role
from reactor.core.settings import Settings


@dataclass(frozen=True)
class ApiKeyRecord:
    key_id: str
    tenant_id: str
    user_id: str
    role: UserRole
    key_sha256: str
    groups: tuple[str, ...] = ()


def api_key_principal_from_header(
    api_key: str | None,
    *,
    settings: Settings,
) -> AuthPrincipal | None:
    if api_key is None or not api_key.strip():
        return None
    presented_hash = sha256(api_key.strip().encode()).hexdigest()
    for record in api_key_records(settings):
        if compare_digest(record.key_sha256, presented_hash):
            return AuthPrincipal(
                user_id=record.user_id,
                tenant_id=record.tenant_id,
                role=record.role,
                groups=record.groups,
            )
    return None


def api_key_records(settings: Settings) -> tuple[ApiKeyRecord, ...]:
    records: list[ApiKeyRecord] = []
    for raw_record in settings.auth_api_keys:
        record = parse_api_key_record(raw_record)
        if record is not None:
            records.append(record)
    return tuple(records)


def parse_api_key_record(value: str) -> ApiKeyRecord | None:
    parts = value.split(":", 5)
    if len(parts) < 5:
        return None
    key_id, tenant_id, user_id, role_value, key_sha256 = (part.strip() for part in parts[:5])
    groups = parse_groups(parts[5]) if len(parts) == 6 else ()
    if not key_id or not tenant_id or not user_id or not is_sha256_hex_digest(key_sha256):
        return None
    return ApiKeyRecord(
        key_id=key_id,
        tenant_id=tenant_id,
        user_id=user_id,
        role=parse_role(role_value),
        key_sha256=key_sha256.lower(),
        groups=groups,
    )


def is_sha256_hex_digest(value: str) -> bool:
    normalized = value.strip().lower()
    return len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized)
