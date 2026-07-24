from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.release.slack_smoke import (
    LiveSlackSmokeConfig,
    SlackAuthTestResult,
    SlackChannelInfoResult,
    SlackPostMessageResult,
    SlackSocketModeResult,
    main,
    run_live_slack_smoke,
)


def test_live_slack_smoke_verifies_signed_request_and_workspace_auth() -> None:
    probe = FakeSlackProbe(auth_result=SlackAuthTestResult(ok=True, team_id="T123", user_id="U123"))

    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ={
            "REACTOR_SLACK_SIGNING_SECRET": "signing-secret",
            "REACTOR_SLACK_BOT_TOKEN": "xoxb-test-token",
        },
        auth_probe=probe,
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "live",
        "evidence": {
            "artifact": "reports/live-slack-workspace-smoke.json",
            "command": (
                "uv run reactor-live-slack-smoke --output reports/live-slack-workspace-smoke.json"
            ),
            "owner": "reactor.release",
            "mode": "live_slack_workspace_smoke",
            "slackGatewaySmoke": {
                "status": "verified",
                "gateway": "native_slack_gateway",
                "ingress": "slash_command_or_socket_mode",
                "currentThreadReplyRoute": "native_gateway",
                "signatureVerificationRequired": True,
                "responseUrlRouteSupported": True,
                "mcpWriteOverlapForbidden": True,
                "requiredChecks": [
                    "required_env",
                    "signed_request",
                    "auth_test",
                    "approval_block_contract",
                ],
            },
        },
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"],
            },
            "signed_request": {"status": "passed"},
            "auth_test": {
                "status": "passed",
                "team_id": "T123",
                "user_id": "U123",
            },
            "channel_info": {
                "status": "skipped",
                "reason": "REACTOR_SLACK_CHANNEL_ID not configured",
            },
            "thread_message": {
                "status": "skipped",
                "reason": "REACTOR_SLACK_CHANNEL_ID not configured",
            },
            "socket_mode": {
                "status": "skipped",
                "reason": "REACTOR_SLACK_APP_TOKEN not configured",
            },
            "approval_block_contract": {
                "status": "passed",
                "actions": ["approval.approve", "approval.reject"],
                "value_fields": [
                    "approvalId",
                    "channelId",
                    "checkpointNs",
                    "runId",
                    "threadId",
                    "threadTs",
                ],
            },
        },
    }
    assert probe.tokens == ["xoxb-test-token"]


def test_live_slack_smoke_verifies_optional_channel_and_socket_mode() -> None:
    probe = FakeSlackProbe(
        auth_result=SlackAuthTestResult(ok=True, team_id="T123", user_id="U123"),
        channel_result=SlackChannelInfoResult(ok=True, channel_id="C123", channel_name="jarvis"),
        root_message_result=SlackPostMessageResult(
            ok=True, channel_id="C123", ts="1782500000.000100"
        ),
        thread_reply_result=SlackPostMessageResult(
            ok=True, channel_id="C123", ts="1782500000.000200"
        ),
        socket_mode_result=SlackSocketModeResult(ok=True, url_present=True),
    )

    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ={
            "REACTOR_SLACK_SIGNING_SECRET": "signing-secret",
            "REACTOR_SLACK_BOT_TOKEN": "xoxb-test-token",
            "REACTOR_SLACK_CHANNEL_ID": "C123",
            "REACTOR_SLACK_APP_TOKEN": "xapp-test-token",
        },
        auth_probe=probe,
    )

    assert report["ok"] is True
    assert report["checks"]["channel_info"] == {
        "status": "passed",
        "channel_id": "C123",
        "channel_name": "jarvis",
    }
    assert report["checks"]["socket_mode"] == {
        "status": "passed",
        "url_present": True,
    }
    assert report["checks"]["thread_message"] == {
        "status": "passed",
        "channel_id": "C123",
        "root_ts_present": True,
        "reply_ts_present": True,
    }
    assert report["checks"]["approval_block_contract"]["status"] == "passed"
    assert probe.channel_calls == [("xoxb-test-token", "C123")]
    assert probe.message_calls == [
        ("xoxb-test-token", "C123", "Reactor live Slack smoke.", None),
        (
            "xoxb-test-token",
            "C123",
            "Reactor live Slack thread smoke.",
            "1782500000.000100",
        ),
    ]
    assert probe.socket_tokens == ["xapp-test-token"]


def test_live_slack_smoke_does_not_block_thread_probe_on_missing_channel_info_scope() -> None:
    probe = FakeSlackProbe(
        auth_result=SlackAuthTestResult(ok=True, team_id="T123", user_id="U123"),
        channel_result=SlackChannelInfoResult(ok=False, error="missing_scope"),
        root_message_result=SlackPostMessageResult(
            ok=True, channel_id="C123", ts="1782500000.000100"
        ),
        thread_reply_result=SlackPostMessageResult(
            ok=True, channel_id="C123", ts="1782500000.000200"
        ),
        socket_mode_result=SlackSocketModeResult(ok=True, url_present=True),
    )

    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ={
            "REACTOR_SLACK_SIGNING_SECRET": "signing-secret",
            "REACTOR_SLACK_BOT_TOKEN": "xoxb-test-token",
            "REACTOR_SLACK_CHANNEL_ID": "C123",
            "REACTOR_SLACK_APP_TOKEN": "xapp-test-token",
        },
        auth_probe=probe,
    )

    assert report["ok"] is True
    assert report["checks"]["channel_info"] == {
        "status": "skipped",
        "reason": "missing Slack scope: conversations.info",
    }
    assert report["checks"]["thread_message"]["status"] == "passed"
    assert report["checks"]["socket_mode"]["status"] == "passed"


def test_live_slack_smoke_skips_when_required_env_is_missing() -> None:
    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ={},
        auth_probe=FakeSlackProbe(auth_result=SlackAuthTestResult(ok=True)),
    )

    assert report == {
        "ok": False,
        "status": "skipped",
        "scope": "live",
        "checks": {
            "required_env": {
                "status": "failed",
                "variables": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"],
                "missing": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"],
            }
        },
        "error": "missing required Slack environment",
    }


def test_live_slack_smoke_records_sanitized_workspace_auth_failure() -> None:
    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ={
            "REACTOR_SLACK_SIGNING_SECRET": "signing-secret",
            "REACTOR_SLACK_BOT_TOKEN": "xoxb-secret-token",
        },
        auth_probe=FakeSlackProbe(
            auth_result=SlackAuthTestResult(
                ok=False,
                error="invalid_auth for xoxb-secret-token",
            )
        ),
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["auth_test"] == {
        "status": "failed",
        "error": "invalid_auth for [redacted]",
    }


def test_live_slack_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "slack-smoke.json"

    monkeypatch.setenv("REACTOR_SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("REACTOR_SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setattr(
        "reactor.release.slack_smoke.HttpSlackProbe",
        fake_http_slack_probe,
    )

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["ok"] is True


class FakeSlackProbe:
    def __init__(
        self,
        *,
        auth_result: SlackAuthTestResult,
        channel_result: SlackChannelInfoResult | None = None,
        socket_mode_result: SlackSocketModeResult | None = None,
        root_message_result: SlackPostMessageResult | None = None,
        thread_reply_result: SlackPostMessageResult | None = None,
    ) -> None:
        self._auth_result = auth_result
        self._channel_result = channel_result or SlackChannelInfoResult(ok=True)
        self._socket_mode_result = socket_mode_result or SlackSocketModeResult(ok=True)
        self._root_message_result = root_message_result or SlackPostMessageResult(
            ok=True, ts="root-ts"
        )
        self._thread_reply_result = thread_reply_result or SlackPostMessageResult(
            ok=True, ts="reply-ts"
        )
        self.tokens: list[str] = []
        self.channel_calls: list[tuple[str, str]] = []
        self.message_calls: list[tuple[str, str, str, str | None]] = []
        self.socket_tokens: list[str] = []

    def auth_test(self, bot_token: str) -> SlackAuthTestResult:
        self.tokens.append(bot_token)
        return self._auth_result

    def channel_info(self, bot_token: str, channel_id: str) -> SlackChannelInfoResult:
        self.channel_calls.append((bot_token, channel_id))
        return self._channel_result

    def socket_mode_open(self, app_token: str) -> SlackSocketModeResult:
        self.socket_tokens.append(app_token)
        return self._socket_mode_result

    def post_message(
        self,
        bot_token: str,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> SlackPostMessageResult:
        self.message_calls.append((bot_token, channel_id, text, thread_ts))
        if thread_ts is None:
            return self._root_message_result
        return self._thread_reply_result


def fake_http_slack_probe(**_: object) -> FakeSlackProbe:
    return FakeSlackProbe(auth_result=SlackAuthTestResult(ok=True, team_id="T123"))
