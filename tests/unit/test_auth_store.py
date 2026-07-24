from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from reactor.auth.models import TokenRevocationRecord, UserRecord
from reactor.auth.rbac import UserRole
from reactor.persistence.auth_store import (
    build_token_revocation_delete,
    build_token_revocation_find,
    build_token_revocation_insert,
    build_token_revoke_upsert,
    build_user_find_by_email,
    build_user_find_by_id,
    build_user_identity_delete_by_external_subject,
    build_user_identity_find_by_external_subject,
    build_user_identity_list_all,
    build_user_identity_upsert,
    build_user_insert,
    build_user_update,
)

TOKEN_ID = "jwt-id-1"  # noqa: S105


def test_user_record_requires_valid_identity_fields() -> None:
    with pytest.raises(ValueError, match="email must contain"):
        UserRecord(
            id="user_1",
            email="not-email",
            name="User",
            password_hash="test-hash",  # noqa: S106
        ).validate()


def test_user_insert_preserves_email_unique_identity_and_role() -> None:
    compiled = build_user_insert(user_record()).compile()

    assert "users" in str(compiled)
    assert compiled.params["id"] == "user_1"
    assert compiled.params["email"] == "user@example.com"
    assert compiled.params["role"] == "ADMIN"
    assert compiled.params["tenant_id"] == "tenant_1"
    assert compiled.params["groups"] == ["engineering", "finance"]


def test_user_update_changes_mutable_fields_by_id() -> None:
    compiled = build_user_update(user_record(role=UserRole.ADMIN_MANAGER)).compile()
    sql = str(compiled)

    assert "UPDATE users" in sql
    assert "users.id =" in sql
    assert compiled.params["role"] == "ADMIN_MANAGER"
    assert compiled.params["groups"] == ["engineering", "finance"]
    assert compiled.params["id_1"] == "user_1"


def test_user_lookup_queries_use_email_or_id() -> None:
    by_email = build_user_find_by_email("user@example.com").compile()
    by_id = build_user_find_by_id("user_1").compile()

    assert "users.email =" in str(by_email)
    assert by_email.params["email_1"] == "user@example.com"
    assert "users.id =" in str(by_id)
    assert by_id.params["id_1"] == "user_1"


def test_user_identity_mapping_upsert_is_tenant_and_provider_scoped() -> None:
    compiled = build_user_identity_upsert(
        tenant_id="tenant_1",
        provider="jira",
        external_subject="acct-123",
        user_id="user_1",
        metadata={"workspace": "ENG"},
    ).compile()
    sql = str(compiled)

    assert "user_identities" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_user_identities_external_subject" in sql
    assert compiled.params["tenant_id"] == "tenant_1"
    assert compiled.params["provider"] == "jira"
    assert compiled.params["external_subject"] == "acct-123"
    assert compiled.params["user_id"] == "user_1"
    assert compiled.params["metadata"] == {"workspace": "ENG"}


def test_user_identity_lookup_filters_tenant_provider_and_external_subject() -> None:
    compiled = build_user_identity_find_by_external_subject(
        tenant_id="tenant_1",
        provider="jira",
        external_subject="acct-123",
    ).compile()
    sql = str(compiled)

    assert "user_identities.tenant_id =" in sql
    assert "user_identities.provider =" in sql
    assert "user_identities.external_subject =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["provider_1"] == "jira"
    assert compiled.params["external_subject_1"] == "acct-123"


def test_user_identity_delete_filters_tenant_provider_and_external_subject() -> None:
    compiled = build_user_identity_delete_by_external_subject(
        tenant_id="tenant_1",
        provider="slack",
        external_subject="U123",
    ).compile()
    sql = str(compiled)

    assert "DELETE FROM user_identities" in sql
    assert "user_identities.tenant_id =" in sql
    assert "user_identities.provider =" in sql
    assert "user_identities.external_subject =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["provider_1"] == "slack"
    assert compiled.params["external_subject_1"] == "U123"


def test_user_identity_list_all_scopes_to_tenant_and_orders_by_updated_at_desc() -> None:
    compiled = build_user_identity_list_all(tenant_id="tenant_1").compile()
    sql = str(compiled)

    assert "FROM user_identities" in sql
    assert "user_identities.tenant_id =" in sql
    assert "ORDER BY user_identities.updated_at DESC" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"


def test_token_revoke_upsert_updates_expiration_on_conflict() -> None:
    expires_at = datetime(2026, 6, 26, tzinfo=UTC) + timedelta(hours=1)
    compiled = build_token_revoke_upsert(TOKEN_ID, expires_at).compile()
    sql = str(compiled)

    assert "auth_token_revocations" in sql
    assert "ON CONFLICT" in sql
    assert compiled.params["token_id"] == TOKEN_ID
    assert compiled.params["expires_at"] == expires_at


def test_token_revocation_insert_preserves_migration_revoked_at() -> None:
    expires_at = datetime(2026, 6, 26, tzinfo=UTC) + timedelta(hours=1)
    revoked_at = datetime(2026, 6, 26, tzinfo=UTC)
    compiled = build_token_revocation_insert(
        TokenRevocationRecord(
            token_id=TOKEN_ID,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )
    ).compile()

    assert "auth_token_revocations" in str(compiled)
    assert "ON CONFLICT" in str(compiled)
    assert compiled.params["token_id"] == TOKEN_ID
    assert compiled.params["expires_at"] == expires_at
    assert compiled.params["revoked_at"] == revoked_at


def test_token_revocation_find_and_delete_scope_to_token_id() -> None:
    find_compiled = build_token_revocation_find(TOKEN_ID).compile()
    delete_compiled = build_token_revocation_delete(TOKEN_ID).compile()

    assert "auth_token_revocations.token_id =" in str(find_compiled)
    assert find_compiled.params["token_id_1"] == TOKEN_ID
    assert "DELETE FROM auth_token_revocations" in str(delete_compiled)
    assert delete_compiled.params["token_id_1"] == TOKEN_ID


def user_record(role: UserRole = UserRole.ADMIN) -> UserRecord:
    return UserRecord(
        id="user_1",
        email="user@example.com",
        name="User",
        password_hash="test-hash",  # noqa: S106
        role=role,
        tenant_id="tenant_1",
        groups=("engineering", "finance"),
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )
