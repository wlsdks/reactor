from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from reactor.slack.reminder import (
    InMemorySlackReminderStore,
    SlackReminderScheduler,
    SlackReminderSchedulerRunner,
)


def test_slack_reminder_store_adds_lists_completes_and_clears_per_user() -> None:
    store = InMemorySlackReminderStore()

    first = store.add("U1", "Follow up with design")
    store.add("U2", "Other user task")
    second = store.add("U1", "Send release note")

    assert first.id == 1
    assert second.id == 2
    assert [reminder.text for reminder in store.list("U1")] == [
        "Follow up with design",
        "Send release note",
    ]
    assert store.done("U1", 1) == first
    assert [reminder.text for reminder in store.list("U1")] == ["Send release note"]
    assert store.clear("U1") == 1
    assert store.list("U1") == []
    assert [reminder.text for reminder in store.list("U2")] == ["Other user task"]


def test_slack_reminder_store_parses_due_time_and_collects_due_reminders() -> None:
    now = datetime(2026, 6, 28, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    store = InMemorySlackReminderStore(
        timezone=ZoneInfo("Asia/Seoul"),
        now=lambda: now,
    )

    reminder = store.add("U1", "Join planning at 10:30")

    assert reminder.text == "Join planning"
    assert reminder.due_at == datetime(2026, 6, 28, 10, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    assert store.collect_due_reminders() == []

    store = InMemorySlackReminderStore(
        timezone=ZoneInfo("Asia/Seoul"),
        now=lambda: now + timedelta(hours=2),
    )
    due = store.add("U1", "Submit report at 10:30")

    assert due.due_at == datetime(2026, 6, 29, 10, 30, tzinfo=ZoneInfo("Asia/Seoul"))

    due_now = datetime(2026, 6, 28, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    due_store = InMemorySlackReminderStore(
        timezone=ZoneInfo("Asia/Seoul"),
        now=lambda: due_now,
    )
    due_store.add("U1", "Check deployment at 10:30")
    due_now = datetime(2026, 6, 28, 11, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    due_reminders = [
        (user_id, reminder.text) for user_id, reminder in due_store.collect_due_reminders()
    ]
    assert due_reminders == [("U1", "Check deployment")]
    assert due_store.list("U1") == []


async def test_slack_reminder_scheduler_sends_due_reminders_as_dm() -> None:
    now = datetime(2026, 6, 28, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    store = InMemorySlackReminderStore(
        timezone=ZoneInfo("Asia/Seoul"),
        now=lambda: now,
    )
    store.add("U1", "Check deployment at 10:30")
    now = datetime(2026, 6, 28, 11, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    messaging_client = RecordingReminderMessagingClient()
    scheduler = SlackReminderScheduler(reminder_store=store, messaging_client=messaging_client)

    delivered = await scheduler.poll_and_notify()

    assert delivered == 1
    assert messaging_client.sent == [
        ("U1", ":bell: *Reminder #1*\nCheck deployment"),
    ]
    assert store.list("U1") == []


async def test_slack_reminder_scheduler_skips_when_no_due_reminders() -> None:
    store = InMemorySlackReminderStore()
    store.add("U1", "No time reminder")
    messaging_client = RecordingReminderMessagingClient()
    scheduler = SlackReminderScheduler(reminder_store=store, messaging_client=messaging_client)

    delivered = await scheduler.poll_and_notify()

    assert delivered == 0
    assert messaging_client.sent == []


async def test_slack_reminder_scheduler_runner_starts_and_closes_loop() -> None:
    scheduler = RecordingPollScheduler()
    runner = SlackReminderSchedulerRunner(scheduler=scheduler, interval_seconds=0.001)

    await runner.start()
    await runner.start()
    await asyncio.sleep(0)
    await runner.close()
    await runner.close()

    assert scheduler.polls >= 1


class RecordingReminderMessagingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_message(
        self,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
        attachments: list[Mapping[str, object]] | None = None,
    ) -> object:
        del thread_ts, attachments
        self.sent.append((channel_id, text))
        return object()


class RecordingPollScheduler:
    def __init__(self) -> None:
        self.polls = 0

    async def poll_and_notify(self) -> int:
        self.polls += 1
        return 0
