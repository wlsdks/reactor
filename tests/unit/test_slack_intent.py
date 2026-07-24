from __future__ import annotations

from reactor.slack.intent import (
    SlackAgentIntent,
    SlackHelpIntent,
    SlackReminderAddIntent,
    SlackReminderClearIntent,
    SlackReminderDoneIntent,
    SlackReminderListIntent,
    parse_slack_slash_intent,
    slack_help_text,
)


def test_slack_slash_intent_parses_help_keywords() -> None:
    assert isinstance(parse_slack_slash_intent("help"), SlackHelpIntent)
    assert isinstance(parse_slack_slash_intent("HELP"), SlackHelpIntent)
    assert isinstance(parse_slack_slash_intent("도움말"), SlackHelpIntent)
    assert isinstance(parse_slack_slash_intent("commands"), SlackHelpIntent)


def test_slack_slash_intent_keeps_help_phrase_as_general_agent_request() -> None:
    intent = parse_slack_slash_intent("help me with deployment")

    assert isinstance(intent, SlackAgentIntent)
    assert intent.mode == "general"
    assert intent.prompt == "help me with deployment"


def test_slack_help_text_shows_post_run_cli_diagnostics() -> None:
    text = slack_help_text("/reactor")

    assert "*After a Run*" in text
    assert "`reactor-runs diagnose <run_id> --output table`" in text
    assert "`reactor-runs replay <run_id> --output table`" in text
    assert "`reactor-admin state-history <run_id> --output table`" in text
    assert "Copy the run id from the bot reply." in text


def test_slack_slash_intent_rewrites_brief_prompt() -> None:
    intent = parse_slack_slash_intent("brief release handoff")

    assert isinstance(intent, SlackAgentIntent)
    assert intent.mode == "brief"
    assert "Create a personal daily brief for the user." in intent.prompt
    assert "Focus: release handoff" in intent.prompt


def test_slack_slash_intent_rewrites_my_work_prompt() -> None:
    intent = parse_slack_slash_intent("my-work sprint board")

    assert isinstance(intent, SlackAgentIntent)
    assert intent.mode == "my_work"
    assert "Summarize my work status as my personal assistant." in intent.prompt
    assert "Scope: sprint board" in intent.prompt


def test_slack_slash_intent_parses_reminder_commands() -> None:
    assert isinstance(parse_slack_slash_intent("remind"), SlackReminderListIntent)
    assert isinstance(parse_slack_slash_intent("remind list"), SlackReminderListIntent)
    assert isinstance(parse_slack_slash_intent("리마인드 목록"), SlackReminderListIntent)
    assert isinstance(parse_slack_slash_intent("remind clear"), SlackReminderClearIntent)
    assert isinstance(parse_slack_slash_intent("리마인드 전체삭제"), SlackReminderClearIntent)

    done_intent = parse_slack_slash_intent("remind done 12")
    add_intent = parse_slack_slash_intent("remind follow up with PM at 4")

    assert isinstance(done_intent, SlackReminderDoneIntent)
    assert done_intent.reminder_id == 12
    assert isinstance(add_intent, SlackReminderAddIntent)
    assert add_intent.text == "follow up with PM at 4"
