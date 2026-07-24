from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from reactor.context.manifest import ContextSection


def render_system_prompt_with_langchain(sections: Sequence[ContextSection]) -> str:
    variables = {section.name: section.model_visible_content() for section in sections}
    template = "\n\n".join(f"[{section.name}]\n{{{section.name}}}" for section in sections)
    messages = ChatPromptTemplate.from_messages([("system", template)]).format_messages(**variables)
    if not messages or not isinstance(messages[0], SystemMessage):
        raise ValueError("LangChain system prompt template did not produce a system message")
    content = messages[0].content
    if isinstance(content, str):
        return content
    return str(content)
