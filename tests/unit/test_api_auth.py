from __future__ import annotations

from hashlib import sha256

from reactor.api.auth import api_key_principal_from_header, api_key_records, parse_api_key_record
from reactor.auth.rbac import UserRole
from reactor.core.settings import Settings


def test_api_key_records_parse_tenant_scoped_hashed_keys() -> None:
    api_key = "reactor-api-key-1"  # noqa: S105
    settings = Settings(
        auth_api_keys=[
            (
                "key_1:tenant_1:service_user:ADMIN_DEVELOPER:"
                f"{sha256(api_key.encode()).hexdigest()}:engineering,ops"
            )
        ]
    )

    records = api_key_records(settings)

    assert len(records) == 1
    assert records[0].key_id == "key_1"
    assert records[0].tenant_id == "tenant_1"
    assert records[0].user_id == "service_user"
    assert records[0].role == UserRole.ADMIN_DEVELOPER
    assert records[0].groups == ("engineering", "ops")


def test_api_key_principal_matches_by_sha256_without_accepting_raw_config_secrets() -> None:
    api_key = "reactor-api-key-1"  # noqa: S105
    settings = Settings(
        auth_api_keys=[
            (f"key_1:tenant_1:service_user:ADMIN:{sha256(api_key.encode()).hexdigest()}"),
            "raw_key:tenant_1:raw_user:ADMIN:reactor-api-key-1",
        ]
    )

    principal = api_key_principal_from_header(api_key, settings=settings)

    assert principal is not None
    assert principal.tenant_id == "tenant_1"
    assert principal.user_id == "service_user"
    assert principal.role == UserRole.ADMIN
    assert api_key_principal_from_header("wrong", settings=settings) is None


def test_parse_api_key_record_ignores_malformed_entries() -> None:
    assert parse_api_key_record("too:few:parts") is None
    assert parse_api_key_record("key:tenant:user:ADMIN:not-a-sha256") is None
