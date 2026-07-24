from __future__ import annotations

from reactor.context.manifest import ContextSection
from reactor.context.prompt_templates import render_system_prompt_with_langchain


def test_langchain_prompt_template_renders_sections_and_preserves_literal_braces() -> None:
    rendered = render_system_prompt_with_langchain(
        [
            ContextSection("system_policy", "Follow Reactor policy."),
            ContextSection(
                "latest_user_request",
                "Explain why {untrusted_context} must stay literal.",
            ),
        ]
    )

    assert rendered == (
        "[system_policy]\n"
        "Follow Reactor policy.\n\n"
        "[latest_user_request]\n"
        "Explain why {untrusted_context} must stay literal."
    )
