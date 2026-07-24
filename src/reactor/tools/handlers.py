from __future__ import annotations

from collections.abc import Mapping

from reactor.tools.execution import ToolExecutionRequest, ToolExecutionResult, ToolHandler

RESERVED_TOOL_NAMESPACES = frozenset({"Slack", "SlackMCP"})


class RoutedToolHandler:
    def __init__(
        self,
        routes: Mapping[str, ToolHandler],
        *,
        fallback: ToolHandler | None = None,
    ) -> None:
        self._routes = dict(routes)
        self._fallback = fallback

    @property
    def route_names(self) -> frozenset[str]:
        return frozenset(self._routes)

    async def __call__(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        handler = self._routes.get(request.tool.qualified_name)
        if handler is not None:
            return await handler(request)
        if request.tool.namespace in RESERVED_TOOL_NAMESPACES:
            return ToolExecutionResult.error(
                "tool_not_configured",
                f"tool handler is not configured for {request.tool.qualified_name}",
            )
        if self._fallback is not None:
            return await self._fallback(request)
        return ToolExecutionResult.error(
            "tool_not_configured",
            f"tool handler is not configured for {request.tool.qualified_name}",
        )
