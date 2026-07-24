from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from reactor.kernel.ids import new_id


def string_list() -> list[str]:
    return []


class A2AAccessPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    peer_agent_id: str | None = Field(default=None, alias="peerAgentId")
    allow_inbound: bool = Field(default=True, alias="allowInbound")
    allow_outbound: bool = Field(default=False, alias="allowOutbound")
    allowed_skills: list[str] = Field(default_factory=string_list, alias="allowedSkills")

    def to_draft(self) -> A2AAccessPolicyDraft:
        return A2AAccessPolicyDraft(
            tenant_id=self.tenant_id,
            peer_agent_id=self.peer_agent_id,
            allow_inbound=self.allow_inbound,
            allow_outbound=self.allow_outbound,
            allowed_skills=self.allowed_skills,
        )


class A2AAccessPolicyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    peer_agent_id: str | None = Field(default=None, alias="peerAgentId")
    allow_inbound: bool = Field(alias="allowInbound")
    allow_outbound: bool = Field(alias="allowOutbound")
    allowed_skills: list[str] = Field(alias="allowedSkills")


@dataclass(frozen=True)
class A2AAccessPolicyDraft:
    tenant_id: str
    peer_agent_id: str | None
    allow_inbound: bool = True
    allow_outbound: bool = False
    allowed_skills: list[str] = field(default_factory=string_list)
    policy_id: str = field(default_factory=lambda: new_id("a2apol"))


@dataclass(frozen=True)
class A2AAccessPolicyView:
    tenant_id: str
    peer_agent_id: str | None
    allow_inbound: bool
    allow_outbound: bool
    allowed_skills: list[str]

    def to_response(self) -> A2AAccessPolicyResponse:
        return A2AAccessPolicyResponse(
            tenantId=self.tenant_id,
            peerAgentId=self.peer_agent_id,
            allowInbound=self.allow_inbound,
            allowOutbound=self.allow_outbound,
            allowedSkills=self.allowed_skills,
        )
