from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, cast


class NextActionStateLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def dependsOnActionIds(self) -> Sequence[str] | None: ...


NextActionStateSource = NextActionStateLike | Mapping[str, object]


def next_action_id(action: NextActionStateSource) -> str:
    if isinstance(action, Mapping):
        value = action.get("id")
    else:
        value = action.id
    return value.strip() if isinstance(value, str) else ""


def next_action_dependencies(action: NextActionStateSource) -> Sequence[str]:
    if isinstance(action, Mapping):
        value = action.get("dependsOnActionIds")
    else:
        value = action.dependsOnActionIds
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ()
    return [
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
    ]


def ready_next_action_ids(actions: Sequence[NextActionStateSource]) -> list[str]:
    return [
        action_id
        for action in actions
        if (action_id := next_action_id(action)) and not next_action_dependencies(action)
    ]


def blocked_next_action_ids(actions: Sequence[NextActionStateSource]) -> list[str]:
    return [
        action_id
        for action in actions
        if (action_id := next_action_id(action)) and next_action_dependencies(action)
    ]


def next_action_states(actions: Sequence[NextActionStateSource]) -> dict[str, str]:
    return {
        action_id: "blocked" if next_action_dependencies(action) else "ready"
        for action in actions
        if (action_id := next_action_id(action))
    }
