from __future__ import annotations

from dataclasses import dataclass

from reactor.api.next_actions import (
    blocked_next_action_ids,
    next_action_states,
    ready_next_action_ids,
)


@dataclass(frozen=True)
class DummyNextAction:
    id: str
    dependsOnActionIds: list[str] | None = None


def test_next_action_state_helpers_derive_ready_and_blocked_actions() -> None:
    actions = [
        DummyNextAction(id="promote-eval"),
        DummyNextAction(id="sync-langsmith", dependsOnActionIds=["preflight-langsmith"]),
    ]

    assert ready_next_action_ids(actions) == ["promote-eval"]
    assert blocked_next_action_ids(actions) == ["sync-langsmith"]
    assert next_action_states(actions) == {
        "promote-eval": "ready",
        "sync-langsmith": "blocked",
    }


def test_next_action_state_helpers_accept_mapping_actions() -> None:
    actions = [
        {"id": "promote-eval"},
        {"id": "sync-langsmith", "dependsOnActionIds": ["preflight-langsmith"]},
    ]

    assert ready_next_action_ids(actions) == ["promote-eval"]
    assert blocked_next_action_ids(actions) == ["sync-langsmith"]
    assert next_action_states(actions) == {
        "promote-eval": "ready",
        "sync-langsmith": "blocked",
    }
