from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from reactor.kernel.ids import new_id


@dataclass(frozen=True)
class SlackBotInstanceRecord:
    id: str = field(default_factory=lambda: new_id("slack_bot"))
    tenant_id: str = "global"
    name: str = ""
    bot_token: str = ""
    app_token: str = ""
    persona_id: str = ""
    default_channel: str | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if len(self.name) > 100:
            raise ValueError("name must not exceed 100 characters")
        if not self.bot_token.strip():
            raise ValueError("botToken is required")
        if not self.app_token.strip():
            raise ValueError("appToken is required")
        if not self.persona_id.strip():
            raise ValueError("personaId is required")

    def updated_with(
        self,
        *,
        name: str | None = None,
        bot_token: str | None = None,
        app_token: str | None = None,
        persona_id: str | None = None,
        default_channel: str | None = None,
        enabled: bool | None = None,
    ) -> SlackBotInstanceRecord:
        return replace(
            self,
            name=name if name is not None else self.name,
            bot_token=bot_token if bot_token is not None else self.bot_token,
            app_token=app_token if app_token is not None else self.app_token,
            persona_id=persona_id if persona_id is not None else self.persona_id,
            default_channel=default_channel
            if default_channel is not None
            else self.default_channel,
            enabled=enabled if enabled is not None else self.enabled,
            updated_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class ProactiveChannelRecord:
    tenant_id: str
    channel_id: str
    channel_name: str | None = None
    added_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.channel_id.strip():
            raise ValueError("channelId must not be blank")
        if len(self.channel_id) > 50:
            raise ValueError("channelId must not exceed 50 characters")
        if self.channel_name is not None and len(self.channel_name) > 200:
            raise ValueError("channelName must not exceed 200 characters")


def mask_slack_token(token: str) -> str:
    return f"{token[:6]}***"
