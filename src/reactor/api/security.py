from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from reactor.core.settings import Settings

CallNext = Callable[[Request], Awaitable[Response]]
NON_ROUTABLE_BIND_HOSTS = frozenset(("0.0.0.0", "::"))  # noqa: S104


def install_security_middleware(app: FastAPI, settings: Settings) -> None:
    limiter = AuthRateLimiter(
        max_attempts_per_minute=settings.auth_login_rate_limit_per_minute,
        trust_forwarded_headers=settings.auth_trust_forwarded_headers,
    )
    app.state.auth_rate_limiter = limiter
    app.middleware("http")(limiter.middleware)
    app.add_middleware(
        RequestBodySizeLimitMiddleware,
        max_body_bytes=settings.request_body_max_bytes,
    )
    if settings.trusted_hosts_enabled:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=trusted_hosts(settings),
        )
    if settings.cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_methods=settings.cors_allowed_methods,
            allow_headers=settings.cors_allowed_headers,
            allow_credentials=settings.cors_allow_credentials,
            max_age=settings.cors_max_age,
        )
    if settings.security_headers_enabled:
        app.middleware("http")(security_headers_middleware)


class RequestBodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = content_length_from_scope(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await send_request_too_large(scope, send, self.max_body_bytes)
            return
        limited_receive = body_size_limited_receive(scope, receive, send, self.max_body_bytes)
        await self.app(scope, limited_receive, send)


def content_length_from_scope(scope: Scope) -> int | None:
    value = Headers(scope=scope).get("content-length")
    if value is None:
        return None
    try:
        length = int(value)
    except ValueError:
        return None
    return max(length, 0)


def body_size_limited_receive(
    scope: Scope,
    receive: Receive,
    send: Send,
    max_body_bytes: int,
) -> Receive:
    consumed = 0
    rejected = False

    async def limited_receive() -> Message:
        nonlocal consumed, rejected
        if rejected:
            return {"type": "http.disconnect"}
        message = await receive()
        if message["type"] != "http.request":
            return message
        body = cast(bytes, message.get("body", b""))
        consumed += len(body)
        if consumed <= max_body_bytes:
            return message
        rejected = True
        await send_request_too_large(scope, send, max_body_bytes)
        return {"type": "http.disconnect"}

    return limited_receive


async def send_request_too_large(scope: Scope, send: Send, max_body_bytes: int) -> None:
    response = JSONResponse(
        status_code=413,
        content={
            "error": "Request body too large.",
            "maxBytes": max_body_bytes,
        },
    )
    await response(scope, receive_disconnect, send)


async def receive_disconnect() -> Message:
    return {"type": "http.disconnect"}


def trusted_hosts(settings: Settings) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for raw_host in [*settings.trusted_hosts, settings.host]:
        host = raw_host.strip().lower()
        if not host or host in NON_ROUTABLE_BIND_HOSTS or host in seen:
            continue
        hosts.append(host)
        seen.add(host)
    return hosts or ["127.0.0.1", "localhost"]


async def security_headers_middleware(request: Request, call_next: CallNext) -> Response:
    response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = content_security_policy(path)
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
    if is_sensitive_path(path):
        response.headers["Cache-Control"] = "no-store"
    return response


def content_security_policy(path: str) -> str:
    if is_swagger_path(path):
        return (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'"
        )
    return "default-src 'self'"


def is_sensitive_path(path: str) -> bool:
    return (
        path.startswith("/api/auth/")
        or path.startswith("/v1/auth/")
        or path.startswith("/api/chat/")
    )


def is_swagger_path(path: str) -> bool:
    return (
        path.startswith("/swagger-ui")
        or path.startswith("/v3/api-docs")
        or path.startswith("/webjars")
    )


@dataclass
class AuthRateLimiter:
    max_attempts_per_minute: int = 10
    trust_forwarded_headers: bool = False
    window_seconds: int = 60
    _failures: dict[str, RateLimitEntry] = field(
        default_factory=lambda: dict[str, RateLimitEntry]()
    )

    async def middleware(self, request: Request, call_next: CallNext) -> Response:
        if not is_rate_limited_auth_path(request.url.path, request.method):
            return await call_next(request)
        key = self.rate_limit_key(request)
        if self.is_blocked(key):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
                content={
                    "error": "Too many authentication attempts. Please try again later.",
                    "details": None,
                },
            )

        response = await call_next(request)
        if 200 <= response.status_code < 300:
            self._failures.pop(key, None)
        elif response.status_code >= 400:
            self.record_failure(key)
        return response

    def rate_limit_key(self, request: Request) -> str:
        return f"{self.client_ip(request)}:{request.url.path}"

    def client_ip(self, request: Request) -> str:
        if self.trust_forwarded_headers:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        return request.client.host if request.client is not None else "unknown"

    def is_blocked(self, key: str) -> bool:
        self.purge_expired()
        entry = self._failures.get(key)
        return entry is not None and entry.count >= self.max_attempts_per_minute

    def record_failure(self, key: str) -> None:
        now = monotonic()
        entry = self._failures.get(key)
        if entry is None or entry.expires_at <= now:
            self._failures[key] = RateLimitEntry(count=1, expires_at=now + self.window_seconds)
            return
        self._failures[key] = RateLimitEntry(
            count=entry.count + 1,
            expires_at=entry.expires_at,
        )

    def purge_expired(self) -> None:
        now = monotonic()
        expired = [key for key, entry in self._failures.items() if entry.expires_at <= now]
        for key in expired:
            self._failures.pop(key, None)


@dataclass(frozen=True)
class RateLimitEntry:
    count: int
    expires_at: float


def is_rate_limited_auth_path(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return path in {"/api/auth/login", "/api/auth/register", "/v1/auth/login", "/v1/auth/register"}
