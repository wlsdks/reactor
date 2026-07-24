from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SlackAgentIntent:
    prompt: str
    mode: Literal["general", "brief", "my_work"]


@dataclass(frozen=True)
class SlackHelpIntent:
    pass


@dataclass(frozen=True)
class SlackReminderAddIntent:
    text: str


@dataclass(frozen=True)
class SlackReminderListIntent:
    pass


@dataclass(frozen=True)
class SlackReminderDoneIntent:
    reminder_id: int


@dataclass(frozen=True)
class SlackReminderClearIntent:
    pass


SlackSlashIntent = (
    SlackAgentIntent
    | SlackHelpIntent
    | SlackReminderAddIntent
    | SlackReminderListIntent
    | SlackReminderDoneIntent
    | SlackReminderClearIntent
)

_HELP_RE = re.compile(r"^(help|도움말|도움|commands)$", re.IGNORECASE)
_BRIEF_RE = re.compile(r"^(brief|브리프)(?:\s+(.*))?$", re.IGNORECASE)
_MY_WORK_RE = re.compile(r"^(my-work|mywork|내업무)(?:\s+(.*))?$", re.IGNORECASE)
_REMIND_RE = re.compile(r"^(remind|리마인드)(?:\s+(.*))?$", re.IGNORECASE)
_REMINDER_DONE_RE = re.compile(r"^(done|완료)\s+(\d+)$", re.IGNORECASE)


def parse_slack_slash_intent(raw_text: str) -> SlackSlashIntent:
    prompt = raw_text.strip()
    if _HELP_RE.fullmatch(prompt):
        return SlackHelpIntent()

    brief_match = _BRIEF_RE.fullmatch(prompt)
    if brief_match is not None:
        return SlackAgentIntent(
            prompt=_build_brief_prompt((brief_match.group(2) or "").strip()),
            mode="brief",
        )

    my_work_match = _MY_WORK_RE.fullmatch(prompt)
    if my_work_match is not None:
        return SlackAgentIntent(
            prompt=_build_my_work_prompt((my_work_match.group(2) or "").strip()),
            mode="my_work",
        )

    reminder_match = _REMIND_RE.fullmatch(prompt)
    if reminder_match is not None:
        return _parse_reminder_intent((reminder_match.group(2) or "").strip())

    return SlackAgentIntent(prompt=prompt, mode="general")


def slack_help_text(command: str) -> str:
    command_name = command.strip() or "/reactor"
    return (
        "*Reactor Commands*\n\n"
        "*General*\n"
        f"`{command_name} <question>` - Ask the agent.\n"
        f"`{command_name} help` - Show this help message.\n\n"
        "*Daily Productivity*\n"
        f"`{command_name} brief [focus]` - Daily brief with priorities and risk check.\n"
        f"`{command_name} my-work [scope]` - Work status summary.\n\n"
        "*After a Run*\n"
        "`reactor-runs diagnose <run_id> --output table` - Inspect status and safe metadata.\n"
        "`reactor-runs replay <run_id> --output table` - Review replayable event history.\n"
        "`reactor-admin state-history <run_id> --output table` - Inspect graph state history.\n"
        "Copy the run id from the bot reply.\n\n"
        "*Tips*\n"
        "- Mention the bot in a channel for a threaded conversation.\n"
        "- React to bot responses to provide feedback."
    )


def _build_brief_prompt(focus: str) -> str:
    normalized_focus = focus or "today's priorities"
    return (
        "Create a personal daily brief for the user.\n"
        f"Focus: {normalized_focus}\n\n"
        "Requirements:\n"
        "- Provide exactly 3 bullet priorities.\n"
        "- Include 1 risk/blocker check.\n"
        "- Include 1 concise next action for the next 60 minutes.\n"
        "- If workspace-specific data is unavailable, make reasonable assumptions and state "
        "them briefly."
    )


def _build_my_work_prompt(scope: str) -> str:
    normalized_scope = scope or "current assigned work items"
    return (
        "Summarize my work status as my personal assistant.\n"
        f"Scope: {normalized_scope}\n\n"
        "Requirements:\n"
        "- Group into: In Progress, Waiting, Next.\n"
        "- Keep each group to at most 3 bullets.\n"
        "- Highlight one item that should be finished first.\n"
        "- If no live data is available, provide a practical checklist template I can fill in "
        "quickly."
    )


def _parse_reminder_intent(argument: str) -> SlackSlashIntent:
    if not argument or argument.lower() == "list" or argument == "목록":
        return SlackReminderListIntent()
    if argument.lower() == "clear" or argument == "전체삭제":
        return SlackReminderClearIntent()
    done_match = _REMINDER_DONE_RE.fullmatch(argument)
    if done_match is not None:
        return SlackReminderDoneIntent(reminder_id=int(done_match.group(2)))
    return SlackReminderAddIntent(text=argument)
