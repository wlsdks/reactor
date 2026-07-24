from __future__ import annotations

from datetime import UTC, datetime

from reactor.auth.jwt import JwtTokenService, claims_from_payload
from reactor.auth.models import UserRecord
from reactor.auth.passwords import hash_password, verify_password
from reactor.auth.rbac import UserRole

SECRET = "x" * 32


def test_password_hash_verification_uses_pbkdf2_and_constant_time_compare() -> None:
    password_hash = hash_password("correct-password", salt=b"0" * 16)

    assert password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_jwt_service_creates_token_with_required_claims() -> None:
    service = JwtTokenService(secret=SECRET, expiration_ms=60_000, default_tenant_id="default")

    token = service.create_token(user_record())
    claims = service.parse_claims(token)

    assert claims is not None
    assert claims.user_id == "user_1"
    assert claims.email == "user@example.com"
    assert claims.role == UserRole.ADMIN
    assert claims.tenant_id == "tenant_1"
    assert claims.groups == ("engineering", "finance")
    assert service.validate_token(token) == "user_1"
    assert service.extract_token_id(token) == claims.token_id
    assert service.extract_expiration(token) == claims.expires_at


def test_jwt_service_rejects_invalid_or_incomplete_payloads() -> None:
    assert (
        JwtTokenService(
            secret=SECRET, expiration_ms=60_000, default_tenant_id="default"
        ).parse_claims("not-a-token")
        is None
    )
    assert claims_from_payload({"sub": "user_1"}) is None


def test_jwt_claims_parse_trusted_groups_from_signed_payload() -> None:
    claims = claims_from_payload(
        {
            "sub": "user_1",
            "jti": "token_1",
            "email": "user@example.com",
            "role": "USER",
            "tenantId": "tenant_1",
            "iat": 1782547200,
            "exp": 1782550800,
            "groups": ["engineering", "finance", "engineering", "", 123],
        }
    )

    assert claims is not None
    assert claims.groups == ("engineering", "finance", "123")


def user_record() -> UserRecord:
    return UserRecord(
        id="user_1",
        email="user@example.com",
        name="User",
        password_hash="test-hash",  # noqa: S106
        role=UserRole.ADMIN,
        tenant_id="tenant_1",
        groups=("engineering", "finance"),
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )
