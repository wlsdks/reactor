from __future__ import annotations


def is_placeholder_env_value(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in {
        "changeme",
        "change-me",
        "placeholder",
        "replace_me",
        "replace-me",
        "tbd",
        "todo",
        "your-api-key",
        "your_api_key",
        "your-token",
        "your_token",
    }:
        return True
    return (normalized.startswith("<") and normalized.endswith(">")) or (
        normalized.startswith("${") and normalized.endswith("}")
    )
