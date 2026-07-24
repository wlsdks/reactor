from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CreateSlackBotRequest(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    botToken: str = Field(min_length=1)
    appToken: str = Field(min_length=1)
    personaId: str = Field(min_length=1)
    defaultChannel: str | None = None
    enabled: bool = True


class UpdateSlackBotRequest(CamelModel):
    name: str | None = Field(default=None, max_length=100)
    botToken: str | None = None
    appToken: str | None = None
    personaId: str | None = None
    defaultChannel: str | None = None
    enabled: bool | None = None


class SlackBotResponse(CamelModel):
    id: str
    name: str
    botTokenMasked: str
    appTokenMasked: str
    personaId: str
    defaultChannel: str | None
    enabled: bool
    createdAt: str
    updatedAt: str


class SlackCommandAckResponse(CamelModel):
    response_type: str = Field(alias="response_type")
    text: str

    @classmethod
    def processing(cls) -> SlackCommandAckResponse:
        return cls(
            response_type="ephemeral",
            text="요청을 처리하고 있습니다. 잠시만 기다려주세요.",
        )

    @classmethod
    def invalid(cls) -> SlackCommandAckResponse:
        return cls(
            response_type="ephemeral",
            text="요청을 처리할 수 없습니다. 필수 Slack 필드가 누락되었습니다.",
        )


class AddProactiveChannelRequest(CamelModel):
    channelId: str = Field(min_length=1, max_length=50)
    channelName: str | None = Field(default=None, max_length=200)


class ProactiveChannelResponse(CamelModel):
    channelId: str
    channelName: str | None
    addedAt: int


class SlackFaqRegistrationRequest(CamelModel):
    channelId: str = Field(min_length=1, max_length=64)
    channelName: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    autoReplyMode: str | None = Field(default=None, max_length=16)
    confidenceThreshold: float | None = None
    daysBack: int | None = None
    reIngestIntervalHours: int | None = None


class SlackFaqRegistrationPatch(CamelModel):
    channelName: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    autoReplyMode: str | None = Field(default=None, max_length=16)
    confidenceThreshold: float | None = None
    daysBack: int | None = None
    reIngestIntervalHours: int | None = None


class SlackFaqRegistrationResponse(CamelModel):
    channelId: str
    channelName: str | None
    enabled: bool
    autoReplyMode: str
    confidenceThreshold: float
    daysBack: int
    reIngestIntervalHours: int
    lastIngestedAt: str | None
    lastMessageCount: int | None
    lastChunkCount: int | None
    lastStatus: str
    lastError: str | None
    registeredBy: str | None
    registeredAt: str
    updatedAt: str


class SlackFaqRegistrationListResponse(CamelModel):
    registrations: list[SlackFaqRegistrationResponse]


class SlackFaqIngestTriggerResponse(CamelModel):
    channelId: str
    status: str
    outboxId: str


class SlackFaqProbeRequest(CamelModel):
    query: str = Field(min_length=1, max_length=2000)
    topK: int | None = Field(default=None, ge=1, le=20)


class SlackFaqDryRunRequest(CamelModel):
    query: str = Field(min_length=1, max_length=2000)
    userId: str | None = Field(default=None, max_length=64)
    asMention: bool | None = None
