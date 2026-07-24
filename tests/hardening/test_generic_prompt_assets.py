from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

PROMPT_ASSET_PATHS = (
    Path("tests/fixtures/agent-eval/regression-suite.json"),
    Path("tests/fixtures/scenarios/minimal-matrix.json"),
    Path("scripts/dev/scenarios/agent-effect-canary.json"),
    Path("scripts/dev/scenarios/user-activity-matrix.json"),
    Path("scripts/dev/scenarios/integration-golden-scenarios.json"),
)

COMPANY_OR_VENDOR_MARKERS = (
    "Acme",
    "ALPHA",
    "LegacyCorp",
    "LegacyOrg",
    "Atlassian",
    "Bitbucket",
    "Confluence",
    "Jira",
    "Jarvis",
    "NeptuneDB",
    "Platform",
    "Slack",
    "SpaceId=ENG",
    "atlassian",
    "bitbucket",
    "confluence",
    "eng",
    "jira",
    "jarvis",
    "kim",
    "lee",
    "#ops",
    "slack",
    "spaceId=ENG",
    "team-alpha",
)

PROMPT_VISIBLE_KEYS = frozenset(
    {
        "arguments",
        "contentContainsAny",
        "contentNotRegex",
        "contentRegexAny",
        "expectedAnswerContains",
        "finalAnswer",
        "forbiddenAnswerContains",
        "jsonRegex",
        "matrix",
        "message",
        "name",
        "source",
        "tags",
        "toolExposure",
        "toolsUsedAll",
        "toolsUsedAny",
        "toolsUsedNone",
        "userInput",
    }
)


def test_bundled_prompt_assets_are_company_and_vendor_neutral() -> None:
    hits: list[str] = []
    for path in PROMPT_ASSET_PATHS:
        payload = json.loads(path.read_text(encoding="utf-8"))
        hits.extend(
            f"{path}:{location}:{marker}"
            for location, value in prompt_visible_values(payload)
            for marker in COMPANY_OR_VENDOR_MARKERS
            if marker in value
        )

    assert hits == []


def prompt_visible_values(
    value: Any,
    *,
    location: str = "$",
    active: bool = False,
) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        if active:
            yield location, value
        return
    if isinstance(value, list):
        items = cast(list[Any], value)
        for index, item in enumerate(items):
            yield from prompt_visible_values(
                item,
                location=f"{location}[{index}]",
                active=active,
            )
        return
    if isinstance(value, Mapping):
        entries = cast(Mapping[str, Any], value)
        for key, item in entries.items():
            key_location = f"{location}.{key}"
            yield from prompt_visible_values(
                item,
                location=key_location,
                active=active or key in PROMPT_VISIBLE_KEYS,
            )
