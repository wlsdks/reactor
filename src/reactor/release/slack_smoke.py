from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, cast

import httpx

from reactor.release.readiness import write_report
from reactor.slack.feedback import SlackInteractionPayload, slack_approval_action_from_payload
from reactor.slack.inbound import SlackSignatureVerifier, build_slack_signature
from reactor.slack.worker import approval_blocks

REQUIRED_SLACK_ENV: tuple[str, ...] = (
    "REACTOR_SLACK_SIGNING_SECRET",
    "REACTOR_SLACK_BOT_TOKEN",
)


@dataclass(frozen=True)
class LiveSlackSmokeConfig:
    timestamp: str = "1782500000"
    body: str = "token=test&team_id=T123&channel_id=C123&user_id=U123&command=%2Freactor&text=ping"
    root_text: str = "Reactor live Slack smoke."
    reply_text: str = "Reactor live Slack thread smoke."
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class SlackAuthTestResult:
    ok: bool
    team_id: str | None = None
    user_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SlackChannelInfoResult:
    ok: bool
    channel_id: str | None = None
    channel_name: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SlackSocketModeResult:
    ok: bool
    url_present: bool = False
    error: str | None = None


@dataclass(frozen=True)
class SlackPostMessageResult:
    ok: bool
    channel_id: str | None = None
    ts: str | None = None
    error: str | None = None


class SlackProbe(Protocol):
    def auth_test(self, bot_token: str) -> SlackAuthTestResult: ...

    def channel_info(self, bot_token: str, channel_id: str) -> SlackChannelInfoResult: ...

    def socket_mode_open(self, app_token: str) -> SlackSocketModeResult: ...

    def post_message(
        self,
        bot_token: str,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> SlackPostMessageResult: ...


class HttpSlackProbe:
    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")

    def auth_test(self, bot_token: str) -> SlackAuthTestResult:
        body = self._post_api("auth.test", token=bot_token)
        if body.get("ok") is True:
            team_id = body.get("team_id")
            user_id = body.get("user_id")
            return SlackAuthTestResult(
                ok=True,
                team_id=team_id if isinstance(team_id, str) else None,
                user_id=user_id if isinstance(user_id, str) else None,
            )
        error = body.get("error")
        return SlackAuthTestResult(
            ok=False,
            error=error if isinstance(error, str) else "slack_api_error",
        )

    def channel_info(self, bot_token: str, channel_id: str) -> SlackChannelInfoResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(
                    f"{self._api_base_url}/conversations.info",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params={"channel": channel_id},
                )
        except httpx.HTTPError as error:
            return SlackChannelInfoResult(ok=False, error=str(error))
        if response.status_code >= 400:
            return SlackChannelInfoResult(ok=False, error=f"http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            return SlackChannelInfoResult(ok=False, error="invalid_response")
        if not isinstance(body, dict):
            return SlackChannelInfoResult(ok=False, error="invalid_response")
        response_body = cast(dict[str, object], body)
        if response_body.get("ok") is True:
            channel = response_body.get("channel")
            channel_body = cast(dict[str, object], channel) if isinstance(channel, dict) else {}
            returned_channel_id = channel_body.get("id")
            channel_name = channel_body.get("name")
            return SlackChannelInfoResult(
                ok=True,
                channel_id=returned_channel_id
                if isinstance(returned_channel_id, str)
                else channel_id,
                channel_name=channel_name if isinstance(channel_name, str) else None,
            )
        error = response_body.get("error")
        return SlackChannelInfoResult(
            ok=False,
            error=error if isinstance(error, str) else "slack_api_error",
        )

    def socket_mode_open(self, app_token: str) -> SlackSocketModeResult:
        body = self._post_api("apps.connections.open", token=app_token)
        if body.get("ok") is True:
            return SlackSocketModeResult(ok=True, url_present=isinstance(body.get("url"), str))
        error = body.get("error")
        return SlackSocketModeResult(
            ok=False,
            error=error if isinstance(error, str) else "slack_api_error",
        )

    def post_message(
        self,
        bot_token: str,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> SlackPostMessageResult:
        payload: dict[str, object] = {
            "channel": channel_id,
            "text": text,
        }
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        body = self._post_api("chat.postMessage", token=bot_token, json_payload=payload)
        if body.get("ok") is True:
            returned_channel_id = body.get("channel")
            ts = body.get("ts")
            return SlackPostMessageResult(
                ok=True,
                channel_id=returned_channel_id
                if isinstance(returned_channel_id, str)
                else channel_id,
                ts=ts if isinstance(ts, str) else None,
            )
        error = body.get("error")
        return SlackPostMessageResult(
            ok=False,
            error=error if isinstance(error, str) else "slack_api_error",
        )

    def _post_api(
        self,
        method: str,
        *,
        token: str,
        json_payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._api_base_url}/{method}",
                    content=json.dumps(dict(json_payload), separators=(",", ":"))
                    if json_payload is not None
                    else None,
                    headers={
                        "Authorization": f"Bearer {token}",
                        **(
                            {"Content-Type": "application/json"} if json_payload is not None else {}
                        ),
                    },
                )
        except httpx.HTTPError as error:
            return {"ok": False, "error": str(error)}
        if response.status_code >= 400:
            return {"ok": False, "error": f"http_{response.status_code}"}
        try:
            body = response.json()
        except ValueError:
            return {"ok": False, "error": "invalid_response"}
        if not isinstance(body, dict):
            return {"ok": False, "error": "invalid_response"}
        return cast(dict[str, object], body)


HttpSlackAuthProbe = HttpSlackProbe


def run_live_slack_smoke(
    config: LiveSlackSmokeConfig,
    *,
    environ: Mapping[str, str],
    auth_probe: SlackProbe,
) -> dict[str, Any]:
    missing_env = [name for name in REQUIRED_SLACK_ENV if not environ.get(name, "").strip()]
    base_report: dict[str, Any] = {
        "scope": "live",
    }
    if missing_env:
        return {
            **base_report,
            "ok": False,
            "status": "skipped",
            "checks": {
                "required_env": {
                    "status": "failed",
                    "variables": list(REQUIRED_SLACK_ENV),
                    "missing": missing_env,
                }
            },
            "error": "missing required Slack environment",
        }

    signing_secret = environ["REACTOR_SLACK_SIGNING_SECRET"]
    bot_token = environ["REACTOR_SLACK_BOT_TOKEN"]
    channel_id = environ.get("REACTOR_SLACK_CHANNEL_ID", "").strip()
    app_token = environ.get("REACTOR_SLACK_APP_TOKEN", "").strip()
    signature = build_slack_signature(signing_secret, config.timestamp, config.body)
    verification = SlackSignatureVerifier(
        signing_secret=signing_secret,
        now_seconds=lambda: int(config.timestamp),
    ).verify(timestamp=config.timestamp, signature=signature, body=config.body)
    if not verification.success:
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": {
                    "status": "passed",
                    "variables": list(REQUIRED_SLACK_ENV),
                },
                "signed_request": {
                    "status": "failed",
                    "error": verification.error_message or "signature verification failed",
                },
            },
        }

    auth_result = auth_probe.auth_test(bot_token)
    if not auth_result.ok:
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": {
                    "status": "passed",
                    "variables": list(REQUIRED_SLACK_ENV),
                },
                "signed_request": {"status": "passed"},
                "auth_test": {
                    "status": "failed",
                    "error": sanitize_error(auth_result.error or "slack_auth_test_failed", environ),
                },
            },
        }

    checks: dict[str, Any] = {
        "required_env": {
            "status": "passed",
            "variables": list(REQUIRED_SLACK_ENV),
        },
        "signed_request": {"status": "passed"},
        "auth_test": {
            "status": "passed",
            "team_id": auth_result.team_id,
            "user_id": auth_result.user_id,
        },
    }
    if channel_id:
        channel_result = auth_probe.channel_info(bot_token, channel_id)
        if not channel_result.ok:
            if channel_result.error == "missing_scope":
                checks["channel_info"] = {
                    "status": "skipped",
                    "reason": "missing Slack scope: conversations.info",
                }
            else:
                checks["channel_info"] = {
                    "status": "failed",
                    "error": sanitize_error(
                        channel_result.error or "slack_channel_info_failed", environ
                    ),
                }
                return {**base_report, "ok": False, "status": "failed", "checks": checks}
        else:
            checks["channel_info"] = {
                "status": "passed",
                "channel_id": channel_result.channel_id,
                "channel_name": channel_result.channel_name,
            }
        root_result = auth_probe.post_message(
            bot_token,
            channel_id=channel_id,
            text=config.root_text,
        )
        if not root_result.ok or root_result.ts is None:
            checks["thread_message"] = {
                "status": "failed",
                "stage": "root_message",
                "error": sanitize_error(root_result.error or "slack_root_message_failed", environ),
            }
            return {**base_report, "ok": False, "status": "failed", "checks": checks}
        reply_result = auth_probe.post_message(
            bot_token,
            channel_id=channel_id,
            text=config.reply_text,
            thread_ts=root_result.ts,
        )
        if not reply_result.ok or reply_result.ts is None:
            checks["thread_message"] = {
                "status": "failed",
                "stage": "thread_reply",
                "error": sanitize_error(reply_result.error or "slack_thread_reply_failed", environ),
            }
            return {**base_report, "ok": False, "status": "failed", "checks": checks}
        checks["thread_message"] = {
            "status": "passed",
            "channel_id": reply_result.channel_id or channel_id,
            "root_ts_present": True,
            "reply_ts_present": True,
        }
    else:
        checks["channel_info"] = {
            "status": "skipped",
            "reason": "REACTOR_SLACK_CHANNEL_ID not configured",
        }
        checks["thread_message"] = {
            "status": "skipped",
            "reason": "REACTOR_SLACK_CHANNEL_ID not configured",
        }

    if app_token:
        socket_mode_result = auth_probe.socket_mode_open(app_token)
        if not socket_mode_result.ok:
            checks["socket_mode"] = {
                "status": "failed",
                "error": sanitize_error(
                    socket_mode_result.error or "slack_socket_mode_failed", environ
                ),
            }
            return {**base_report, "ok": False, "status": "failed", "checks": checks}
        checks["socket_mode"] = {
            "status": "passed",
            "url_present": socket_mode_result.url_present,
        }
    else:
        checks["socket_mode"] = {
            "status": "skipped",
            "reason": "REACTOR_SLACK_APP_TOKEN not configured",
        }
    checks["approval_block_contract"] = approval_block_contract_check()

    return {
        **base_report,
        "ok": True,
        "status": "passed",
        "evidence": slack_gateway_smoke_evidence(),
        "checks": checks,
    }


def slack_gateway_smoke_evidence() -> dict[str, object]:
    return {
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
    }


def approval_block_contract_check() -> dict[str, object]:
    result = SimpleNamespace(
        run_id="run_smoke",
        thread_id="thread_smoke",
        checkpoint_ns="reactor",
        response_metadata={
            "approval_status": "pending",
            "approval_request": {"tool_risk_level": "high"},
        },
    )
    blocks = approval_blocks(
        approval_id="approval_smoke",
        result=result,
        tool_id="Slack:smoke_tool",
        requested_by="U_SMOKE",
        channel_id="C_SMOKE",
        thread_ts="1782500000.000100",
    )
    actions_block = next(
        (block for block in blocks if block.get("type") == "actions"),
        None,
    )
    if not isinstance(actions_block, Mapping):
        return {"status": "failed", "error": "approval actions block missing"}
    raw_elements = actions_block.get("elements")
    if not isinstance(raw_elements, list):
        return {"status": "failed", "error": "approval actions elements missing"}
    elements = cast(list[object], raw_elements)

    action_ids: list[str] = []
    common_value_fields: set[str] | None = None
    for element in elements:
        if not isinstance(element, Mapping):
            return {"status": "failed", "error": "approval action element invalid"}
        element_map = cast(Mapping[str, object], element)
        action_id = element_map.get("action_id")
        value = element_map.get("value")
        if not isinstance(action_id, str) or not isinstance(value, str):
            return {"status": "failed", "error": "approval action id/value invalid"}
        parsed_value = json.loads(value)
        if not isinstance(parsed_value, dict):
            return {"status": "failed", "error": "approval action value invalid"}
        parsed_value_map = cast(dict[str, object], parsed_value)
        value_fields: set[str] = {
            key for key, field_value in parsed_value_map.items() if isinstance(field_value, str)
        }
        common_value_fields = (
            value_fields
            if common_value_fields is None
            else common_value_fields.intersection(value_fields)
        )
        action = slack_approval_action_from_payload(
            SlackInteractionPayload(
                type="block_actions",
                action_id=action_id,
                value=value,
                user_id="U_APPROVER",
                channel_id="C_SMOKE",
                message_ts="1782500000.000200",
                trigger_id="trigger_smoke",
                response_url="https://hooks.slack.test/interaction",
            )
        )
        if action is None:
            return {"status": "failed", "error": "approval action parser rejected value"}
        action_ids.append(action_id)

    return {
        "status": "passed",
        "actions": action_ids,
        "value_fields": sorted(common_value_fields or set()),
    }


def sanitize_error(message: str, environ: Mapping[str, str]) -> str:
    sanitized = message
    for value in environ.values():
        if value and len(value) >= 6:
            sanitized = sanitized.replace(value, "[redacted]")
    return sanitized


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live Slack workspace smoke check.")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="Slack API timeout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = LiveSlackSmokeConfig(timeout_seconds=float(args.timeout_seconds))
    report = run_live_slack_smoke(
        config,
        environ=os.environ,
        auth_probe=HttpSlackProbe(timeout_seconds=config.timeout_seconds),
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
