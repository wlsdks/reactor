from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from reactor.observability.tracing import redact_span_attribute_value

INSTRUCTION_LIKE_PATTERNS = (
    "ignore previous instructions",
    "reveal system prompt",
    "send secrets",
)
CANARY_PATTERN = re.compile(r"REACTOR_CANARY_SECRET_[A-Za-z0-9_\\-]+")
TOOL_OUTPUT_SANITIZER_FINDINGS = frozenset(
    {
        "tool_output_truncated",
        "instruction_like_tool_output",
        "canary_secret",
        "secret_like_tool_output",
    }
)
MODEL_VISIBLE_AUTHORIZATION_KEYS = frozenset(
    {
        "acl",
        "acl_proof",
        "acl_hash",
        "acl_visibility",
        "acl_users",
        "acl_groups",
    }
)


@dataclass(frozen=True)
class SanitizedToolOutput:
    model_visible_text: str
    findings: list[str]


def model_visible_tool_output(value: object) -> object:
    """Project a tool result without model-visible authorization evidence."""
    if isinstance(value, Mapping):
        visible: dict[str, object] = {}
        for key, item in cast(Mapping[object, object], value).items():
            safe_key = str(key)
            if is_authorization_output_key(safe_key):
                continue
            visible[safe_key] = model_visible_tool_output(item)
        return visible
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [model_visible_tool_output(item) for item in cast(Sequence[object], value)]
    return value


def is_authorization_output_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in MODEL_VISIBLE_AUTHORIZATION_KEYS or normalized.startswith(
        ("acl_user_", "acl_group_")
    )


def sanitize_tool_output(output: str, *, max_chars: int = 8_000) -> SanitizedToolOutput:
    findings: list[str] = []
    text = output[:max_chars]
    if len(output) > max_chars:
        findings.append("tool_output_truncated")
    lowered = text.lower()
    if any(pattern in lowered for pattern in INSTRUCTION_LIKE_PATTERNS):
        findings.append("instruction_like_tool_output")
    if CANARY_PATTERN.search(text):
        findings.append("canary_secret")
        text = CANARY_PATTERN.sub("[REDACTED_CANARY]", text)
    redacted = str(redact_span_attribute_value(text))
    if redacted != text:
        findings.append("secret_like_tool_output")
        text = redacted
    return SanitizedToolOutput(
        model_visible_text=f"[tool_output:data]\n{text}",
        findings=findings,
    )
