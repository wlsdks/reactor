from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class FollowupImpression:
    suggestion_id: str
    category: str
    channel_id: str
    user_id: str
    message_ts: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FollowupClick:
    suggestion_id: str
    category: str
    channel_id: str
    user_id: str
    message_ts: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryFollowupSuggestionStore:
    def __init__(self, *, retention_hours: int = 72, max_events: int = 50_000) -> None:
        self.retention_hours = retention_hours
        self.max_events = max_events
        self._impressions: list[FollowupImpression] = []
        self._clicks: list[FollowupClick] = []

    def record_impression(self, event: FollowupImpression) -> None:
        self._impressions.append(event)
        self._trim(now=event.occurred_at)

    def record_click(self, event: FollowupClick) -> None:
        self._clicks.append(event)
        self._trim(now=event.occurred_at)

    def aggregate_stats(
        self,
        *,
        window_hours: int = 24,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current_time = now or datetime.now(UTC)
        since = current_time - timedelta(hours=window_hours)
        impressions = [event for event in self._impressions if event.occurred_at > since]
        clicks = [event for event in self._clicks if event.occurred_at > since]
        categories = sorted({event.category for event in impressions + clicks})
        by_category = [
            category_stats(
                category=category,
                impressions=[event for event in impressions if event.category == category],
                clicks=[event for event in clicks if event.category == category],
            )
            for category in categories
        ]
        by_category.sort(key=category_clicks_sort_key, reverse=True)
        return {
            "totalImpressions": len(impressions),
            "totalClicks": len(clicks),
            "ctr": ctr(len(clicks), len(impressions)),
            "byCategory": by_category,
        }

    def _trim(self, *, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now(UTC)) - timedelta(hours=self.retention_hours)
        self._impressions = [event for event in self._impressions if event.occurred_at > cutoff]
        self._clicks = [event for event in self._clicks if event.occurred_at > cutoff]
        overflow = max(0, len(self._impressions) + len(self._clicks) - self.max_events)
        if overflow:
            self._impressions = self._impressions[overflow:]


def category_stats(
    *,
    category: str,
    impressions: list[FollowupImpression],
    clicks: list[FollowupClick],
) -> dict[str, object]:
    return {
        "category": category,
        "impressions": len(impressions),
        "clicks": len(clicks),
        "ctr": ctr(len(clicks), len(impressions)),
    }


def category_clicks_sort_key(item: dict[str, object]) -> int:
    clicks = item.get("clicks", 0)
    return clicks if isinstance(clicks, int) else 0


def ctr(clicks: int, impressions: int) -> float:
    return clicks / impressions if impressions > 0 else 0.0
