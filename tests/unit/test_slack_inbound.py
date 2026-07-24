from __future__ import annotations

import hmac
from hashlib import sha256

from reactor.slack.inbound import (
    InMemorySlackEventDeduplicator,
    SlackSignatureVerifier,
    build_slack_command_idempotency_key,
    build_slack_event_idempotency_key,
)

SLACK_TEST_SIGNING_SECRET = "secret"  # noqa: S105
SLACK_PREVIOUS_SIGNING_SECRET = "old-secret"  # noqa: S105


def test_slack_signature_verifier_accepts_valid_hmac() -> None:
    body = '{"event_id":"Ev123"}'
    timestamp = "1782500000"
    signature = slack_signature(SLACK_TEST_SIGNING_SECRET, timestamp, body)

    result = SlackSignatureVerifier(
        signing_secret=SLACK_TEST_SIGNING_SECRET,
        timestamp_tolerance_seconds=300,
        now_seconds=lambda: 1782500000,
    ).verify(timestamp=timestamp, signature=signature, body=body)

    assert result.success is True
    assert result.error_message is None


def test_slack_signature_verifier_accepts_previous_secret_during_rotation() -> None:
    body = '{"event_id":"Ev123"}'
    timestamp = "1782500000"
    signature = slack_signature(SLACK_PREVIOUS_SIGNING_SECRET, timestamp, body)

    result = SlackSignatureVerifier(
        signing_secret=SLACK_TEST_SIGNING_SECRET,
        previous_signing_secrets=[SLACK_PREVIOUS_SIGNING_SECRET],
        timestamp_tolerance_seconds=300,
        now_seconds=lambda: 1782500000,
    ).verify(timestamp=timestamp, signature=signature, body=body)

    assert result.success is True
    assert result.error_message is None


def test_slack_signature_verifier_rejects_when_no_rotation_secret_matches() -> None:
    body = '{"event_id":"Ev123"}'
    timestamp = "1782500000"
    signature = slack_signature("other-secret", timestamp, body)

    result = SlackSignatureVerifier(
        signing_secret=SLACK_TEST_SIGNING_SECRET,
        previous_signing_secrets=[SLACK_PREVIOUS_SIGNING_SECRET],
        timestamp_tolerance_seconds=300,
        now_seconds=lambda: 1782500000,
    ).verify(timestamp=timestamp, signature=signature, body=body)

    assert result.success is False
    assert result.error_message == "Signature mismatch"


def test_slack_signature_verifier_fails_closed_for_missing_secret_or_stale_timestamp() -> None:
    missing_secret = SlackSignatureVerifier(
        signing_secret="",
        now_seconds=lambda: 1782500000,
    ).verify(timestamp="1782500000", signature="v0=abc", body="{}")
    stale = SlackSignatureVerifier(
        signing_secret=SLACK_TEST_SIGNING_SECRET,
        timestamp_tolerance_seconds=300,
        now_seconds=lambda: 1782501000,
    ).verify(
        timestamp="1782500000",
        signature=slack_signature(SLACK_TEST_SIGNING_SECRET, "1782500000", "{}"),
        body="{}",
    )

    assert missing_secret.success is False
    assert missing_secret.error_message == "Signing secret not configured"
    assert stale.success is False
    assert stale.error_message == "Timestamp too old or too new (tolerance: 300s)"


def test_slack_event_deduplicator_marks_recent_event_once() -> None:
    deduplicator = InMemorySlackEventDeduplicator(ttl_seconds=600, now_seconds=lambda: 1000)

    assert deduplicator.is_duplicate_and_mark("Ev123") is False
    assert deduplicator.is_duplicate_and_mark("Ev123") is True


def test_slack_idempotency_keys_are_stable() -> None:
    assert build_slack_event_idempotency_key("tenant_1", "Ev123") == "slack:event:tenant_1:Ev123"
    assert (
        build_slack_command_idempotency_key("tenant_1", "T1", "U1", "123.456")
        == "slack:command:tenant_1:T1:U1:123.456"
    )


def test_slack_command_idempotency_key_disambiguates_missing_trigger_commands() -> None:
    status_key = build_slack_command_idempotency_key(
        "tenant_1",
        "T1",
        "U1",
        None,
        command="/reactor",
        channel_id="C1",
        text="status",
    )
    help_key = build_slack_command_idempotency_key(
        "tenant_1",
        "T1",
        "U1",
        None,
        command="/reactor",
        channel_id="C1",
        text="help",
    )

    assert status_key != help_key
    assert status_key.startswith("slack:command:tenant_1:T1:U1:missing-trigger:")
    assert help_key.startswith("slack:command:tenant_1:T1:U1:missing-trigger:")


def slack_signature(secret: str, timestamp: str, body: str) -> str:
    base = f"v0:{timestamp}:{body}".encode()
    digest = hmac.new(secret.encode(), base, sha256).hexdigest()
    return f"v0={digest}"
