from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    enabled: bool = True

    def validate(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("provider", self.provider),
            ("model", self.model),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class ProviderFallback:
    from_provider: str
    from_model: str
    to_provider: str
    to_model: str
    reason: str
    latency_ms: int
    cost_usd: float

    def as_metadata(self) -> dict[str, object]:
        return {
            "from_provider": self.from_provider,
            "from_model": self.from_model,
            "to_provider": self.to_provider,
            "to_model": self.to_model,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
        }


class ProviderRouter:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        if not profiles:
            raise ValueError("at least one model profile is required")
        for profile in profiles:
            profile.validate()
        self._profiles = profiles

    def select_profile(self, preferred_name: str | None = None) -> ModelProfile:
        if preferred_name is not None:
            for profile in self._profiles:
                if profile.name == preferred_name and profile.enabled:
                    return profile
        for profile in self._profiles:
            if profile.enabled:
                return profile
        raise ValueError("no enabled model profile is available")

    def select_fallback_profile(
        self,
        *,
        failed_provider: str,
        failed_model: str,
        reason: str,
        latency_ms: int,
        cost_usd: float,
    ) -> tuple[ModelProfile, ProviderFallback]:
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")
        for profile in self._profiles:
            if not profile.enabled:
                continue
            if profile.provider == failed_provider and profile.model == failed_model:
                continue
            fallback = ProviderFallback(
                from_provider=failed_provider,
                from_model=failed_model,
                to_provider=profile.provider,
                to_model=profile.model,
                reason=reason,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )
            return profile, fallback
        raise ValueError("no fallback model profile is available")
