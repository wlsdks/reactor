from __future__ import annotations

from reactor.tools.sanitizer import sanitize_tool_output


def test_sanitize_tool_output_redacts_secret_shaped_values() -> None:
    sanitized = sanitize_tool_output(
        "provider failed with api_key=sk-live-1234567890abcdef and token ghp_abcdef1234567890"
    )

    assert "sk-live-1234567890abcdef" not in sanitized.model_visible_text
    assert "ghp_abcdef1234567890" not in sanitized.model_visible_text
    assert "api_key=[REDACTED]" in sanitized.model_visible_text
    assert sanitized.findings == ["secret_like_tool_output"]
