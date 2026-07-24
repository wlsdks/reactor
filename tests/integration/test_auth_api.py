from __future__ import annotations

from datetime import datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.auth.jwt import JwtTokenService
from reactor.auth.models import UserRecord
from reactor.auth.service import AuthResult
from reactor.core.settings import Settings

SECRET = "x" * 32
REACTOR_EXCHANGE_TOKEN = "reactor-jwt"  # noqa: S105


async def test_auth_register_respects_disabled_local_self_registration() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "password-1", "name": "User"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Self-registration is disabled. Contact an administrator."


async def test_local_demo_login_supports_me_logout_and_revocation() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post("/api/auth/demo-login")
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = await client.get("/api/auth/me", headers=headers)
        logout = await client.post("/api/auth/logout", headers=headers)
        revoked_me = await client.get("/api/auth/me", headers=headers)

    assert login.status_code == 200
    assert login.json()["user"]["role"] == "ADMIN"
    assert me.status_code == 200
    assert me.json()["email"] == "demo@reactor.local"
    assert logout.status_code == 200
    assert revoked_me.status_code == 401
    assert revoked_me.json()["detail"] == "token is revoked"


async def test_auth_register_login_me_and_logout_flow() -> None:
    app = create_app()
    user_store = FakeUserStore()
    token_store = FakeTokenRevocationStore()
    app.state.reactor = FakeContainer(user_store=user_store, token_store=token_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register = await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "password-1", "name": "User"},
        )
        login = await client.post(
            "/v1/auth/login",
            json={"email": "user@example.com", "password": "password-1"},
        )
        token = login.json()["token"]
        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        logout = await client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        revoked_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert register.status_code == 201
    assert register.json()["user"]["role"] == "ADMIN"
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"
    assert logout.status_code == 200
    assert token_store.revoked_token_id is not None
    assert revoked_me.status_code == 401
    assert revoked_me.json()["detail"] == "token is revoked"


async def test_auth_login_rejects_invalid_credentials() -> None:
    app = create_app()
    user_store = FakeUserStore()
    await user_store.save(
        UserRecord(
            id="user_1",
            email="user@example.com",
            name="User",
            password_hash="pbkdf2_sha256$1$00$00",  # noqa: S106
        )
    )
    app.state.reactor = FakeContainer(user_store=user_store, token_store=FakeTokenRevocationStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_auth_rejects_invalid_bearer_token_without_header_fallback() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        user_store=FakeUserStore(),
        token_store=FakeTokenRevocationStore(),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/auth/me",
            headers={
                "Authorization": "Bearer not-a-valid-jwt",
                "X-Reactor-User-Id": "spoofed_admin",
                "X-Reactor-Role": "ADMIN",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid bearer token"


async def test_auth_fails_closed_when_jwt_revocation_store_is_unavailable() -> None:
    user = UserRecord(
        id="user_1",
        email="user@example.com",
        name="User",
        password_hash="pbkdf2_sha256$fixture",  # noqa: S106
    )
    user_store = FakeUserStore()
    await user_store.save(user)
    token = JwtTokenService(
        secret=SECRET,
        expiration_ms=60_000,
        default_tenant_id="default",
    ).create_token(user)
    app = create_app()
    app.state.reactor = FakeContainer(user_store=user_store, token_store=None)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert response.json()["detail"] == "token revocation persistence is not configured"


async def test_auth_change_password_updates_hash_and_requires_current_password() -> None:
    app = create_app()
    user_store = FakeUserStore()
    token_store = FakeTokenRevocationStore()
    app.state.reactor = FakeContainer(user_store=user_store, token_store=token_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register = await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "password-1", "name": "User"},
        )
        token = register.json()["token"]
        bad = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"currentPassword": "wrong-password", "newPassword": "password-2"},
        )
        good = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"currentPassword": "password-1", "newPassword": "password-2"},
        )
        login_old = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password-1"},
        )
        login_new = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password-2"},
        )

    assert bad.status_code == 400
    assert good.status_code == 200
    assert good.json() == {"message": "Password changed successfully"}
    assert login_old.status_code == 401
    assert login_new.status_code == 200


async def test_auth_demo_login_creates_or_promotes_admin_user() -> None:
    app = create_app()
    user_store = FakeUserStore()
    app.state.reactor = FakeContainer(user_store=user_store, token_store=FakeTokenRevocationStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/auth/demo-login")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "demo@reactor.local"
    assert body["user"]["role"] == "ADMIN"
    assert body["token"]


async def test_auth_demo_login_is_unavailable_outside_local_environment() -> None:
    app = create_app()
    user_store = FakeUserStore()
    app.state.reactor = FakeContainer(
        user_store=user_store,
        token_store=FakeTokenRevocationStore(),
        settings=Settings(
            environment="production",
            auth_jwt_secret=SECRET,
            auth_demo_login_enabled=True,
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/auth/demo-login")

    assert response.status_code == 404
    assert await user_store.count() == 0


async def test_auth_exchange_returns_404_when_iam_exchange_is_disabled() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        user_store=FakeUserStore(),
        token_store=FakeTokenRevocationStore(),
        iam_exchange_service=None,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/auth/exchange", json={"token": "iam-token"})

    assert response.status_code == 404
    assert response.json()["detail"] == "IAM token exchange is not enabled"


async def test_auth_exchange_rejects_invalid_iam_token() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        user_store=FakeUserStore(),
        token_store=FakeTokenRevocationStore(),
        iam_exchange_service=FakeIamExchangeService(result=None),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/auth/exchange", json={"token": "bad-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "IAM token verification failed"


async def test_auth_exchange_returns_reactor_token_and_user() -> None:
    user = UserRecord(
        id="iam-user-1",
        email="iam@example.com",
        name="IAM User",
        password_hash="iam-external",  # noqa: S106
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        user_store=FakeUserStore(),
        token_store=FakeTokenRevocationStore(),
        iam_exchange_service=FakeIamExchangeService(
            result=AuthResult(token=REACTOR_EXCHANGE_TOKEN, user=user)
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/auth/exchange", json={"token": "valid-iam-token"})

    assert response.status_code == 200
    assert response.json()["token"] == REACTOR_EXCHANGE_TOKEN
    assert response.json()["user"]["email"] == "iam@example.com"


class FakeContainer:
    def __init__(
        self,
        user_store: FakeUserStore,
        token_store: FakeTokenRevocationStore | None,
        iam_exchange_service: FakeIamExchangeService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings(
            auth_jwt_secret=SECRET,
            auth_self_registration_enabled=True,
            auth_default_tenant_id="default",
        )
        self._user_store = user_store
        self._token_store = token_store
        self._iam_exchange_service = iam_exchange_service

    def user_store(self) -> FakeUserStore:
        return self._user_store

    def token_revocation_store(self) -> FakeTokenRevocationStore | None:
        return self._token_store

    def iam_token_exchange_service(self) -> FakeIamExchangeService | None:
        return self._iam_exchange_service


class FakeUserStore:
    def __init__(self) -> None:
        self.users_by_id: dict[str, UserRecord] = {}
        self.users_by_email: dict[str, UserRecord] = {}

    async def find_by_email(self, email: str) -> UserRecord | None:
        return self.users_by_email.get(email)

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: UserRecord) -> UserRecord:
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        return user

    async def update(self, user: UserRecord) -> UserRecord:
        return await self.save(user)

    async def exists_by_email(self, email: str) -> bool:
        return email in self.users_by_email

    async def count(self) -> int:
        return len(self.users_by_id)


class FakeTokenRevocationStore:
    def __init__(self) -> None:
        self.revoked_token_id: str | None = None
        self.revoked_expires_at: datetime | None = None

    async def revoke(self, token_id: str, expires_at: datetime) -> None:
        self.revoked_token_id = token_id
        self.revoked_expires_at = expires_at

    async def is_revoked(self, token_id: str) -> bool:
        return self.revoked_token_id == token_id


class FakeIamExchangeService:
    def __init__(self, result: AuthResult | None) -> None:
        self.result = result

    async def exchange(self, iam_token: str) -> AuthResult | None:
        return self.result
