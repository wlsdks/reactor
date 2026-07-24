from __future__ import annotations

from dataclasses import dataclass

from reactor.prompts.profiles import ToolForcingMode, ToolForcingPolicy


@dataclass(frozen=True)
class GraphProfile:
    profile_id: str
    prompt_version: str
    model_provider: str
    model: str
    tool_allowlist: list[str]
    max_tool_calls: int = 10
    temperature: float = 1.0
    checkpoint_ns: str = "reactor"
    max_tools_per_request: int = 60
    tool_forcing_policy: ToolForcingPolicy | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("profile_id", self.profile_id),
            ("prompt_version", self.prompt_version),
            ("model_provider", self.model_provider),
            ("model", self.model),
            ("checkpoint_ns", self.checkpoint_ns),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls must be non-negative")
        if self.max_tools_per_request <= 0:
            raise ValueError("max_tools_per_request must be positive")
        if len(self.tool_allowlist) > self.max_tools_per_request:
            raise ValueError("tool_allowlist exceeds max_tools_per_request")
        if self.tool_forcing_policy is not None:
            self.tool_forcing_policy.validate()


class GraphProfileRegistry:
    def __init__(self, profiles: list[GraphProfile]) -> None:
        self._profiles = {profile.profile_id: profile for profile in profiles}
        for profile in profiles:
            profile.validate()

    def get(self, profile_id: str) -> GraphProfile:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"unknown graph profile: {profile_id}")
        return profile


def standard_graph_profile() -> GraphProfile:
    return GraphProfile(
        profile_id="standard",
        prompt_version="standard-v1",
        model_provider="openai",
        model="gpt-5-mini",
        tool_allowlist=[],
        max_tool_calls=10,
        temperature=1.0,
        checkpoint_ns="reactor",
    )


def rag_graph_profile() -> GraphProfile:
    return GraphProfile(
        profile_id="rag",
        prompt_version="rag-v1",
        model_provider="openai",
        model="gpt-5-mini",
        tool_allowlist=["Rag:hybrid_search"],
        max_tool_calls=6,
        temperature=0.2,
        checkpoint_ns="reactor-rag",
    )


def research_graph_profile() -> GraphProfile:
    return GraphProfile(
        profile_id="research",
        prompt_version="research-v1",
        model_provider="openai",
        model="gpt-5-mini",
        tool_allowlist=["Rag:hybrid_search"],
        max_tool_calls=8,
        temperature=0.2,
        checkpoint_ns="reactor-research",
        max_tools_per_request=20,
        tool_forcing_policy=ToolForcingPolicy(
            mode=ToolForcingMode.FORCE_ONE,
            forced_tool="Rag:hybrid_search",
        ),
    )


def default_graph_profile_registry() -> GraphProfileRegistry:
    return GraphProfileRegistry(
        [
            standard_graph_profile(),
            rag_graph_profile(),
            research_graph_profile(),
        ]
    )
