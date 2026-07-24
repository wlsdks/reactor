from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.api.security import install_security_middleware
from reactor.core.container import AppContainer
from reactor.core.settings import Settings


async def test_security_headers_are_added_to_api_responses() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert response.headers["X-XSS-Protection"] == "0"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains; preload"
    )
    assert response.headers["Permissions-Policy"] == (
        "geolocation=(), camera=(), microphone=(), payment=()"
    )


async def test_security_headers_mark_auth_paths_no_store() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login", json={"email": "bad@example.com", "password": "x"}
        )

    assert response.headers["Cache-Control"] == "no-store"


async def test_cors_is_opt_in_and_uses_configured_origin() -> None:
    settings = Settings(cors_enabled=True, cors_allowed_origins=["https://app.example"])
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://app.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example"


async def test_trusted_host_middleware_rejects_unconfigured_host_header() -> None:
    settings = Settings(trusted_hosts=["api.reactor.example"])
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://evil.example") as client:
        response = await client.get("/healthz")

    assert response.status_code == 400
    assert response.text == "Invalid host header"


async def test_trusted_host_middleware_allows_configured_host_header() -> None:
    settings = Settings(trusted_hosts=["api.reactor.example"])
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://api.reactor.example") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200


async def test_request_body_size_limit_rejects_oversized_payload_before_handler() -> None:
    settings = Settings(request_body_max_bytes=16)
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/chat", content=b"x" * 17)

    assert response.status_code == 413
    assert response.json() == {
        "error": "Request body too large.",
        "maxBytes": 16,
    }


async def test_request_body_size_limit_allows_payload_within_configured_limit() -> None:
    settings = Settings(request_body_max_bytes=256)
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/chat", json={"message": "small"})

    assert response.status_code == 200


async def test_auth_rate_limit_blocks_failed_login_attempts_and_sets_retry_after() -> None:
    settings = Settings(auth_login_rate_limit_per_minute=2)
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/auth/login",
            json={"email": "bad@example.com", "password": "wrong"},
        )
        second = await client.post(
            "/api/auth/login",
            json={"email": "bad@example.com", "password": "wrong"},
        )
        blocked = await client.post(
            "/api/auth/login",
            json={"email": "bad@example.com", "password": "wrong"},
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.json()["error"] == "Too many authentication attempts. Please try again later."


async def test_auth_rate_limit_does_not_apply_to_get_me() -> None:
    settings = Settings(auth_login_rate_limit_per_minute=1)
    app = create_app()
    app.user_middleware.clear()
    app.middleware_stack = None
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/api/auth/me")
        second = await client.get("/api/auth/me")

    assert first.status_code != 429
    assert second.status_code != 429
