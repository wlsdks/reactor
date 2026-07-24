from __future__ import annotations

from datetime import UTC, datetime

from reactor.auth.models import UserRecord


class InMemoryUserStore:
    """Process-local auth storage for the explicitly non-durable local runtime."""

    def __init__(self) -> None:
        self._users_by_id: dict[str, UserRecord] = {}
        self._user_ids_by_email: dict[str, str] = {}

    async def find_by_email(self, email: str) -> UserRecord | None:
        user_id = self._user_ids_by_email.get(email)
        return self._users_by_id.get(user_id) if user_id is not None else None

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        return self._users_by_id.get(user_id)

    async def save(self, user: UserRecord) -> UserRecord:
        user.validate()
        previous = self._users_by_id.get(user.id)
        if previous is not None and previous.email != user.email:
            self._user_ids_by_email.pop(previous.email, None)
        self._users_by_id[user.id] = user
        self._user_ids_by_email[user.email] = user.id
        return user

    async def update(self, user: UserRecord) -> UserRecord:
        if user.id not in self._users_by_id:
            raise LookupError(f"unknown local user: {user.id}")
        return await self.save(user)

    async def exists_by_email(self, email: str) -> bool:
        return email in self._user_ids_by_email

    async def count(self) -> int:
        return len(self._users_by_id)


class InMemoryTokenRevocationStore:
    """Process-local JWT revocations paired with the local ephemeral signing key."""

    def __init__(self) -> None:
        self._expires_at_by_token_id: dict[str, datetime] = {}

    async def revoke(self, token_id: str, expires_at: datetime) -> None:
        if expires_at > datetime.now(UTC):
            self._expires_at_by_token_id[token_id] = expires_at

    async def is_revoked(self, token_id: str) -> bool:
        expires_at = self._expires_at_by_token_id.get(token_id)
        if expires_at is None:
            return False
        if expires_at <= datetime.now(UTC):
            self._expires_at_by_token_id.pop(token_id, None)
            return False
        return True
