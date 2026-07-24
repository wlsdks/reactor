from __future__ import annotations

from datetime import UTC, datetime, timedelta

from reactor.followup import (
    FollowupClick,
    FollowupImpression,
    InMemoryFollowupSuggestionStore,
)

NOW = datetime(2026, 6, 26, 12, tzinfo=UTC)


def test_followup_store_aggregates_windowed_ctr_by_category() -> None:
    store = InMemoryFollowupSuggestionStore()
    store.record_impression(impression("s1", "jira", occurred_at=NOW - timedelta(hours=1)))
    store.record_impression(impression("s2", "jira", occurred_at=NOW - timedelta(hours=1)))
    store.record_impression(impression("s3", "docs", occurred_at=NOW - timedelta(hours=1)))
    store.record_click(click("s1", "jira", occurred_at=NOW - timedelta(minutes=30)))
    store.record_click(click("s4", "stale", occurred_at=NOW - timedelta(hours=30)))

    stats = store.aggregate_stats(window_hours=24, now=NOW)

    assert stats == {
        "totalImpressions": 3,
        "totalClicks": 1,
        "ctr": 1 / 3,
        "byCategory": [
            {"category": "jira", "impressions": 2, "clicks": 1, "ctr": 0.5},
            {"category": "docs", "impressions": 1, "clicks": 0, "ctr": 0.0},
        ],
    }


def impression(
    suggestion_id: str,
    category: str,
    *,
    occurred_at: datetime,
) -> FollowupImpression:
    return FollowupImpression(
        suggestion_id=suggestion_id,
        category=category,
        channel_id="C1",
        user_id="U1",
        occurred_at=occurred_at,
    )


def click(
    suggestion_id: str,
    category: str,
    *,
    occurred_at: datetime,
) -> FollowupClick:
    return FollowupClick(
        suggestion_id=suggestion_id,
        category=category,
        channel_id="C1",
        user_id="U1",
        occurred_at=occurred_at,
    )
