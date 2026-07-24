from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from reactor.auth.api_keys import (
    ApiKeyRecord,
    api_key_principal_from_header,
    api_key_records,
    parse_api_key_record,
)
from reactor.auth.jwt import JwtTokenService
from reactor.auth.rbac import (
    ANONYMOUS_USER_ID,
    AuthPrincipal,
    UserRole,
    local_identity_headers_allowed,
    parse_groups,
    parse_role,
)
from reactor.core.settings import Settings, get_settings

__all__ = [
    "ApiKeyRecord",
    "api_key_principal_from_header",
    "api_key_records",
    "parse_api_key_record",
]


async def principal_from_headers(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_reactor_user_id: Annotated[str | None, Header(alias="X-Reactor-User-Id")] = None,
    x_reactor_tenant_id: Annotated[str | None, Header(alias="X-Reactor-Tenant-Id")] = None,
    x_reactor_role: Annotated[str | None, Header(alias="X-Reactor-Role")] = None,
    x_reactor_admin: Annotated[str | None, Header(alias="X-Reactor-Admin")] = None,
    x_reactor_groups: Annotated[str | None, Header(alias="X-Reactor-Groups")] = None,
    x_reactor_api_key: Annotated[str | None, Header(alias="X-Reactor-API-Key")] = None,
) -> AuthPrincipal:
    settings = auth_settings_from_request(request)
    token_principal = await token_principal_from_request(request, authorization)
    if token_principal is not None:
        return token_principal
    api_key_principal = api_key_principal_from_header(
        x_reactor_api_key,
        settings=settings,
    )
    if api_key_principal is not None:
        return api_key_principal
    if x_reactor_api_key is not None and x_reactor_api_key.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    if not local_identity_headers_allowed(settings.environment):
        return AuthPrincipal(
            user_id=ANONYMOUS_USER_ID,
            tenant_id=settings.auth_default_tenant_id,
            role=UserRole.USER,
        )
    role = parse_role(x_reactor_role)
    if role == UserRole.USER and truthy(x_reactor_admin):
        role = UserRole.ADMIN
    return AuthPrincipal(
        user_id=(x_reactor_user_id or "anonymous").strip() or "anonymous",
        tenant_id=(x_reactor_tenant_id or "local").strip() or "local",
        role=role,
        groups=parse_groups(x_reactor_groups),
    )


PRINCIPAL_DEPENDENCY = Depends(principal_from_headers)


def require_permission(permission: str):
    def dependency(principal: AuthPrincipal = PRINCIPAL_DEPENDENCY) -> AuthPrincipal:
        if not principal.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"permission required: {permission}",
            )
        return principal

    return dependency


def require_developer_admin(
    principal: AuthPrincipal = PRINCIPAL_DEPENDENCY,
) -> AuthPrincipal:
    if not principal.is_developer_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return principal


def require_any_admin(principal: AuthPrincipal = PRINCIPAL_DEPENDENCY) -> AuthPrincipal:
    if not principal.is_any_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return principal


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def principal_from_authorization_header(
    authorization: str | None,
    *,
    settings: Settings | None = None,
) -> AuthPrincipal | None:
    if authorization is None or not authorization.startswith("Bearer "):
        return None
    actual_settings = settings or get_settings()
    if not actual_settings.auth_jwt_secret:
        return None
    try:
        service = JwtTokenService(
            secret=actual_settings.auth_jwt_secret,
            expiration_ms=actual_settings.auth_jwt_expiration_ms,
            default_tenant_id=actual_settings.auth_default_tenant_id,
        )
    except ValueError:
        return None
    claims = service.parse_claims(authorization.removeprefix("Bearer ").strip())
    if claims is None:
        return None
    return AuthPrincipal(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        role=claims.role,
        groups=claims.groups,
    )


async def token_principal_from_request(
    request: Request,
    authorization: str | None,
) -> AuthPrincipal | None:
    if authorization is None or not authorization.startswith("Bearer "):
        return None
    settings = auth_settings_from_request(request)
    token = authorization.removeprefix("Bearer ").strip()
    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )
    try:
        service = JwtTokenService(
            secret=settings.auth_jwt_secret,
            expiration_ms=settings.auth_jwt_expiration_ms,
            default_tenant_id=settings.auth_default_tenant_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    claims = service.parse_claims(token)
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    revocation_store = token_revocation_store_from_request(request)
    if revocation_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token revocation persistence is not configured",
        )
    if await revocation_store.is_revoked(claims.token_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token is revoked")
    return AuthPrincipal(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        role=claims.role,
        groups=claims.groups,
    )


def auth_settings_from_request(request: Request) -> Settings:
    reactor = getattr(request.app.state, "reactor", None)
    settings = getattr(reactor, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


def token_revocation_store_from_request(request: Request):
    reactor = getattr(request.app.state, "reactor", None)
    if reactor is None or not hasattr(reactor, "token_revocation_store"):
        return None
    return reactor.token_revocation_store()
