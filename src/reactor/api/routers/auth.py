from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from reactor.api.auth import bearer_token, principal_from_headers
from reactor.api.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenExchangeRequest,
    UserResponse,
)
from reactor.auth.jwt import JwtTokenService
from reactor.auth.models import UserRecord
from reactor.auth.rbac import AuthPrincipal
from reactor.auth.service import AuthService
from reactor.core.container import AppContainer

router = APIRouter(tags=["auth"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def jwt_service(container: AppContainer) -> JwtTokenService:
    if not container.settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )
    try:
        return JwtTokenService(
            secret=container.settings.auth_jwt_secret,
            expiration_ms=container.settings.auth_jwt_expiration_ms,
            default_tenant_id=container.settings.auth_default_tenant_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


def auth_service(request: Request) -> AuthService:
    container = get_container(request)
    user_store = container.user_store()
    if user_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user persistence is not configured",
        )
    return AuthService(
        user_store=user_store,
        jwt_tokens=jwt_service(container),
        self_registration_enabled=container.settings.auth_self_registration_enabled,
    )


@router.post(
    "/api/auth/register",
    response_model=AuthResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/auth/register",
    response_model=AuthResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def register(request: Request, body: RegisterRequest) -> AuthResponse:
    service = auth_service(request)
    try:
        result = await service.register(email=body.email, password=body.password, name=body.name)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except FileExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return AuthResponse(token=result.token, user=user_response(result.user))


@router.post("/api/auth/login", response_model=AuthResponse, response_model_by_alias=True)
@router.post("/v1/auth/login", response_model=AuthResponse, response_model_by_alias=True)
async def login(request: Request, body: LoginRequest) -> AuthResponse:
    service = auth_service(request)
    result = await service.login(email=body.email, password=body.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return AuthResponse(token=result.token, user=user_response(result.user))


@router.post("/api/auth/demo-login", response_model=AuthResponse, response_model_by_alias=True)
@router.post("/v1/auth/demo-login", response_model=AuthResponse, response_model_by_alias=True)
async def demo_login(request: Request) -> AuthResponse:
    container = get_container(request)
    if (
        container.settings.environment.strip().lower() != "local"
        or not container.settings.auth_demo_login_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Demo login is not enabled"
        )
    result = await auth_service(request).demo_login()
    return AuthResponse(token=result.token, user=user_response(result.user))


@router.post("/api/auth/exchange", response_model=AuthResponse, response_model_by_alias=True)
@router.post("/v1/auth/exchange", response_model=AuthResponse, response_model_by_alias=True)
async def exchange(request: Request, body: TokenExchangeRequest) -> AuthResponse:
    service = get_container(request).iam_token_exchange_service()
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IAM token exchange is not enabled",
        )
    result = await service.exchange(body.token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="IAM token verification failed",
        )
    return AuthResponse(token=result.token, user=user_response(result.user))


@router.get("/api/auth/me", response_model=UserResponse, response_model_by_alias=True)
@router.get("/v1/auth/me", response_model=UserResponse, response_model_by_alias=True)
async def me(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> UserResponse:
    service = auth_service(request)
    user = await service.get_user(principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_response(user)


@router.post("/api/auth/change-password")
@router.post("/v1/auth/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> dict[str, str]:
    changed = await auth_service(request).change_password(
        user_id=principal.user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    return {"message": "Password changed successfully"}


@router.post("/api/auth/logout")
@router.post("/v1/auth/logout")
async def logout(request: Request, token: Annotated[str, Depends(bearer_token)]) -> dict[str, str]:
    container = get_container(request)
    revocation_store = container.token_revocation_store()
    if revocation_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token revocation persistence is not configured",
        )
    token_service = jwt_service(container)
    token_id = token_service.extract_token_id(token)
    expires_at = token_service.extract_expiration(token)
    if token_id is None or expires_at is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    await revocation_store.revoke(token_id, expires_at)
    return {"message": "Logged out"}


def user_response(user: UserRecord) -> UserResponse:
    admin_scope = user.role.admin_scope()
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        adminScope=admin_scope.value if admin_scope is not None else None,
        tenantId=user.tenant_id,
    )
