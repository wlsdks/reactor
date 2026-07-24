from __future__ import annotations

import hmac
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    error_message: str | None = None

    @classmethod
    def ok(cls) -> VerificationResult:
        return cls(success=True)

    @classmethod
    def failure(cls, reason: str) -> VerificationResult:
        return cls(success=False, error_message=reason)


class SlackSignatureVerifier:
    def __init__(
        self,
        *,
        signing_secret: str,
        previous_signing_secrets: Sequence[str] = (),
        timestamp_tolerance_seconds: int = 300,
        now_seconds: Callable[[], int] | None = None,
    ) -> None:
        self._signing_secret = signing_secret
        self._previous_signing_secrets = previous_signing_secrets
        self._timestamp_tolerance_seconds = timestamp_tolerance_seconds
        self._now_seconds = now_seconds or (lambda: int(time.time()))

    def verify(
        self, *, timestamp: str | None, signature: str | None, body: str
    ) -> VerificationResult:
        if not self._signing_secret.strip():
            return VerificationResult.failure("Signing secret not configured")
        if not timestamp:
            return VerificationResult.failure("Missing X-Slack-Request-Timestamp header")
        if not signature:
            return VerificationResult.failure("Missing X-Slack-Signature header")
        try:
            request_timestamp = int(timestamp)
        except ValueError:
            return VerificationResult.failure("Invalid timestamp format")

        if abs(self._now_seconds() - request_timestamp) > self._timestamp_tolerance_seconds:
            return VerificationResult.failure(
                f"Timestamp too old or too new (tolerance: {self._timestamp_tolerance_seconds}s)"
            )

        for secret in self._candidate_secrets():
            expected = build_slack_signature(secret, timestamp, body)
            if hmac.compare_digest(expected.encode(), signature.encode()):
                return VerificationResult.ok()
        return VerificationResult.failure("Signature mismatch")

    def _candidate_secrets(self) -> list[str]:
        return [
            secret
            for secret in (self._signing_secret, *self._previous_signing_secrets)
            if secret.strip()
        ]


class InMemorySlackEventDeduplicator:
    def __init__(
        self,
        *,
        ttl_seconds: int = 600,
        enabled: bool = True,
        now_seconds: Callable[[], int] | None = None,
    ) -> None:
        self._ttl_seconds = max(1, ttl_seconds)
        self._enabled = enabled
        self._now_seconds = now_seconds or (lambda: int(time.time()))
        self._seen: dict[str, int] = {}

    def is_duplicate_and_mark(self, event_id: str) -> bool:
        if self.is_duplicate(event_id):
            return True
        self.mark(event_id)
        return False

    def is_duplicate(self, event_id: str) -> bool:
        if not self._enabled or not event_id.strip():
            return False
        now = self._now_seconds()
        self._cleanup(now)
        return event_id in self._seen

    def mark(self, event_id: str) -> None:
        if not self._enabled or not event_id.strip():
            return
        now = self._now_seconds()
        self._cleanup(now)
        self._seen[event_id] = now

    def _cleanup(self, now: int) -> None:
        expired = [
            event_id
            for event_id, seen_at in self._seen.items()
            if now - seen_at > self._ttl_seconds
        ]
        for event_id in expired:
            self._seen.pop(event_id, None)


def build_slack_signature(secret: str, timestamp: str, body: str) -> str:
    base = f"v0:{timestamp}:{body}".encode()
    return f"v0={hmac.new(secret.encode(), base, sha256).hexdigest()}"


def build_slack_event_idempotency_key(tenant_id: str, event_id: str) -> str:
    return f"slack:event:{tenant_id}:{event_id}"


def build_slack_command_idempotency_key(
    tenant_id: str,
    team_id: str,
    user_id: str,
    trigger_id: str | None,
    *,
    command: str | None = None,
    channel_id: str | None = None,
    text: str | None = None,
) -> str:
    normalized_trigger_id = (trigger_id or "").strip()
    if normalized_trigger_id and normalized_trigger_id != "missing-trigger":
        return f"slack:command:{tenant_id}:{team_id}:{user_id}:{normalized_trigger_id}"

    context_fingerprint = sha256(
        "\x1f".join(
            [
                (command or "").strip(),
                (channel_id or "").strip(),
                (text or "").strip(),
            ]
        ).encode()
    ).hexdigest()[:16]
    return f"slack:command:{tenant_id}:{team_id}:{user_id}:missing-trigger:{context_fingerprint}"
