from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SlackReminder:
    id: int
    text: str
    due_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ReminderParseResult:
    clean_text: str
    due_at: datetime | None


class SlackReminderMessagingClient(Protocol):
    async def send_message(
        self,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
        attachments: list[Mapping[str, object]] | None = None,
    ) -> object: ...


class SlackReminderPoller(Protocol):
    async def poll_and_notify(self) -> int: ...


_AT_TIME_RE = re.compile(r"(?:^|\s)at\s+(\d{1,2}):(\d{2})(?:\s*$)", re.IGNORECASE)
_KOREAN_TIME_RE = re.compile(r"(?:^|\s)(\d{1,2})시(?:\s*(\d{1,2})분)?(?:\s*에?)(?:\s*$)")


class InMemorySlackReminderStore:
    def __init__(
        self,
        *,
        max_per_user: int = 50,
        timezone: ZoneInfo | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._max_per_user = max(1, max_per_user)
        self._timezone = timezone or ZoneInfo("Asia/Seoul")
        self._now = now or (lambda: datetime.now(self._timezone))
        self._reminders_by_user: dict[str, list[SlackReminder]] = {}
        self._sequence_by_user: dict[str, int] = {}

    def add(self, user_id: str, text: str) -> SlackReminder:
        parsed = parse_reminder_time(text.strip(), timezone=self._timezone, now=self._now)
        reminder = SlackReminder(
            id=self._next_id(user_id),
            text=parsed.clean_text,
            due_at=parsed.due_at,
            created_at=self._aware_now(),
        )
        reminders = self._reminders_by_user.setdefault(user_id, [])
        reminders.append(reminder)
        del reminders[: max(0, len(reminders) - self._max_per_user)]
        return reminder

    def list(self, user_id: str) -> list[SlackReminder]:
        return sorted(self._reminders_by_user.setdefault(user_id, []), key=lambda item: item.id)

    def done(self, user_id: str, reminder_id: int) -> SlackReminder | None:
        reminders = self._reminders_by_user.setdefault(user_id, [])
        for reminder in reminders:
            if reminder.id == reminder_id:
                reminders.remove(reminder)
                return reminder
        return None

    def clear(self, user_id: str) -> int:
        reminders = self._reminders_by_user.setdefault(user_id, [])
        count = len(reminders)
        reminders.clear()
        return count

    def collect_due_reminders(self) -> list[tuple[str, SlackReminder]]:
        now = self._aware_now()
        due: list[tuple[str, SlackReminder]] = []
        for user_id, reminders in self._reminders_by_user.items():
            ready = [
                reminder
                for reminder in reminders
                if reminder.due_at is not None and reminder.due_at <= now
            ]
            if not ready:
                continue
            ready_ids = {reminder.id for reminder in ready}
            self._reminders_by_user[user_id] = [
                reminder for reminder in reminders if reminder.id not in ready_ids
            ]
            due.extend((user_id, reminder) for reminder in ready)
        return due

    def _next_id(self, user_id: str) -> int:
        current = self._sequence_by_user.get(user_id, 0) + 1
        self._sequence_by_user[user_id] = current
        return current

    def _aware_now(self) -> datetime:
        now = self._now()
        if now.tzinfo is None:
            return now.replace(tzinfo=self._timezone)
        return now.astimezone(self._timezone)


class SlackReminderScheduler:
    def __init__(
        self,
        *,
        reminder_store: InMemorySlackReminderStore,
        messaging_client: SlackReminderMessagingClient,
    ) -> None:
        self._reminder_store = reminder_store
        self._messaging_client = messaging_client

    async def poll_and_notify(self) -> int:
        try:
            due_reminders = self._reminder_store.collect_due_reminders()
        except Exception:
            return 0

        delivered = 0
        for user_id, reminder in due_reminders:
            with suppress(Exception):
                await self._messaging_client.send_message(
                    channel_id=user_id,
                    text=f":bell: *Reminder #{reminder.id}*\n{reminder.text}",
                )
                delivered += 1
        return delivered


class SlackReminderSchedulerRunner:
    def __init__(
        self,
        *,
        scheduler: SlackReminderPoller,
        interval_seconds: float = 60.0,
    ) -> None:
        self._scheduler = scheduler
        self._interval_seconds = max(0.001, interval_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="slack-reminder-scheduler")

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            await self._scheduler.poll_and_notify()
            await asyncio.sleep(self._interval_seconds)


def parse_reminder_time(
    text: str,
    *,
    timezone: ZoneInfo,
    now: Callable[[], datetime],
) -> ReminderParseResult:
    at_match = _AT_TIME_RE.search(text)
    if at_match is not None:
        return _parse_match(text, at_match, timezone=timezone, now=now)

    korean_match = _KOREAN_TIME_RE.search(text)
    if korean_match is not None:
        return _parse_match(text, korean_match, timezone=timezone, now=now)

    return ReminderParseResult(clean_text=text, due_at=None)


def _parse_match(
    text: str,
    match: re.Match[str],
    *,
    timezone: ZoneInfo,
    now: Callable[[], datetime],
) -> ReminderParseResult:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour not in range(24) or minute not in range(60):
        return ReminderParseResult(clean_text=text, due_at=None)
    current = now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    current = current.astimezone(timezone)
    due_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due_at <= current:
        due_at += timedelta(days=1)
    clean_text = (text[: match.start()] + text[match.end() :]).strip()
    return ReminderParseResult(clean_text=clean_text or text.strip(), due_at=due_at)
