from __future__ import annotations

from reactor.auth.iam import fetch_public_key, role_from_iam_roles
from reactor.auth.rbac import UserRole


def test_iam_role_mapping_prefers_admin_roles() -> None:
    assert (
        role_from_iam_roles(["ROLE_DEVELOPER", "ROLE_ADMIN"], default_role=UserRole.USER)
        == UserRole.ADMIN
    )
    assert (
        role_from_iam_roles(["ROLE_MANAGER"], default_role=UserRole.USER) == UserRole.ADMIN_MANAGER
    )
    assert (
        role_from_iam_roles(["ROLE_DEVELOPER"], default_role=UserRole.USER)
        == UserRole.ADMIN_DEVELOPER
    )
    assert role_from_iam_roles([], default_role=UserRole.USER) == UserRole.USER


def test_iam_public_key_fetch_returns_none_for_unreachable_server() -> None:
    assert fetch_public_key("http://127.0.0.1:1", timeout_ms=100) is None
