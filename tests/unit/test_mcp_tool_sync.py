from __future__ import annotations

import asyncio
import socket
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from reactor.mcp.registry import McpServerRegistration, McpToolSnapshot
from reactor.tools.mcp.adapter import (
    build_tool_snapshot_hash,
    langchain_mcp_connection,
    load_langchain_mcp_tools,
    qualify_loaded_mcp_tools,
    sync_mcp_tools_to_specs,
)


def test_mcp_tool_snapshot_hash_is_stable() -> None:
    snapshots = [
        McpToolSnapshot(
            tenant_id="tenant_1",
            server_name="SearchServer",
            tool_name="search_docs",
            description="Search docs.",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            output_schema={"type": "object"},
        )
    ]

    assert build_tool_snapshot_hash(snapshots) == build_tool_snapshot_hash(
        list(reversed(snapshots))
    )


def test_mcp_tool_sync_converts_snapshots_to_reactor_tool_specs() -> None:
    snapshots = [
        McpToolSnapshot(
            tenant_id="tenant_1",
            server_name="SearchServer",
            tool_name="search_docs",
            description="Search docs.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        McpToolSnapshot(
            tenant_id="tenant_1",
            server_name="SearchServer",
            tool_name="write_doc",
            description="Write docs.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level="write",
        ),
    ]

    specs = sync_mcp_tools_to_specs(snapshots)

    assert [spec.qualified_name for spec in specs] == [
        "SearchServer:search_docs",
        "SearchServer:write_doc",
    ]
    assert specs[1].approval_required is True


def test_mcp_tool_sync_excludes_disabled_snapshots_from_model_facing_specs() -> None:
    snapshots = [
        McpToolSnapshot(
            tenant_id="tenant_1",
            server_name="SearchServer",
            tool_name="search_docs",
            description="Search docs.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            enabled=True,
        ),
        McpToolSnapshot(
            tenant_id="tenant_1",
            server_name="SearchServer",
            tool_name="delete_doc",
            description="Delete docs.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level="destructive",
            enabled=False,
        ),
    ]

    specs = sync_mcp_tools_to_specs(snapshots)

    assert [spec.qualified_name for spec in specs] == ["SearchServer:search_docs"]


def test_langchain_mcp_connection_maps_stdio_registration_to_official_shape() -> None:
    connection = langchain_mcp_connection(
        McpServerRegistration(
            tenant_id="tenant_1",
            name="Docs",
            transport="stdio",
            command="uvx",
            args=("docs-mcp", "--readonly"),
            timeout_ms=12_000,
        )
    )

    assert connection == {
        "transport": "stdio",
        "command": "uvx",
        "args": ["docs-mcp", "--readonly"],
        "session_kwargs": {"read_timeout_seconds": timedelta(seconds=12)},
    }


def test_langchain_mcp_connection_maps_streamable_http_registration_to_official_shape() -> None:
    connection = langchain_mcp_connection(
        McpServerRegistration(
            tenant_id="tenant_1",
            name="Docs",
            transport="streamable_http",
            url="https://mcp.example.com/mcp",
            timeout_ms=15_000,
        )
    )

    assert connection == {
        "transport": "streamable_http",
        "url": "https://mcp.example.com/mcp",
        "timeout": timedelta(seconds=15),
    }


def test_langchain_mcp_connection_requires_bound_credentials_for_auth() -> None:
    with pytest.raises(ValueError, match="credential binding"):
        langchain_mcp_connection(
            McpServerRegistration(
                tenant_id="tenant_1",
                name="Docs",
                transport="streamable_http",
                url="https://mcp.example.com/mcp",
                auth_type="bearer",
            )
        )


async def test_load_langchain_mcp_tools_uses_official_loader_and_reactor_tool_names() -> None:
    calls: list[dict[str, object]] = []

    async def fake_loader(
        session: object,
        **kwargs: object,
    ) -> list[FakeLangChainTool]:
        calls.append({"session": session, **kwargs})
        return [FakeLangChainTool("search_docs")]

    tools = await load_langchain_mcp_tools(
        [
            McpServerRegistration(
                tenant_id="tenant_1",
                name="Docs",
                transport="streamable_http",
                url="https://mcp.example.com/mcp",
            )
        ],
        loader=fake_loader,
    )

    assert [tool.name for tool in tools] == ["Docs:search_docs"]
    assert calls[0]["session"] is None
    assert calls[0]["server_name"] == "Docs"
    assert calls[0]["tool_name_prefix"] is False
    assert calls[0]["handle_tool_errors"] is True
    assert calls[0]["connection"] == {
        "transport": "streamable_http",
        "url": "https://mcp.example.com/mcp",
        "timeout": timedelta(seconds=15),
    }


async def test_load_langchain_mcp_tools_smokes_live_stdio_transport(tmp_path: Path) -> None:
    server_file = tmp_path / "stdio_mcp_server.py"
    write_live_mcp_server(server_file)

    tools = await load_langchain_mcp_tools(
        [
            McpServerRegistration(
                tenant_id="tenant_1",
                name="Docs",
                transport="stdio",
                command=sys.executable,
                args=(str(server_file),),
                timeout_ms=5_000,
            )
        ],
    )

    assert [tool.name for tool in tools] == ["Docs:search_docs"]
    result = await cast(Any, tools[0]).ainvoke({"query": "langgraph"})
    assert result[0]["type"] == "text"
    assert result[0]["text"] == "result:langgraph"


async def test_load_langchain_mcp_tools_smokes_live_streamable_http_transport(
    tmp_path: Path,
) -> None:
    server_file = tmp_path / "http_mcp_server.py"
    write_live_mcp_server(server_file)
    port = free_tcp_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(server_file),
        "streamable-http",
        str(port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        wait_for_tcp_port(port)
        tools = await load_langchain_mcp_tools(
            [
                McpServerRegistration(
                    tenant_id="tenant_1",
                    name="Docs",
                    transport="streamable_http",
                    url=f"http://127.0.0.1:{port}/mcp",
                    timeout_ms=5_000,
                )
            ],
        )

        assert [tool.name for tool in tools] == ["Docs:search_docs"]
        result = await cast(Any, tools[0]).ainvoke({"query": "http"})
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "result:http"
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)


def test_qualify_loaded_mcp_tools_normalizes_official_underscore_prefix() -> None:
    tools = qualify_loaded_mcp_tools(
        [FakeLangChainTool("Docs_search"), FakeLangChainTool("Docs:read")],
        server_name="Docs",
    )

    assert [tool.name for tool in tools] == ["Docs:search", "Docs:read"]


def test_qualify_loaded_mcp_tools_rejects_cross_server_qualified_name() -> None:
    with pytest.raises(ValueError, match="unexpected MCP tool namespace"):
        qualify_loaded_mcp_tools(
            [FakeLangChainTool("OtherServer:read")],
            server_name="Docs",
        )


class FakeLangChainTool:
    def __init__(self, name: str) -> None:
        self.name = name


def write_live_mcp_server(path: Path) -> None:
    path.write_text(
        """
import sys
from mcp.server.fastmcp import FastMCP

transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
mcp = FastMCP("Docs", host="127.0.0.1", port=port)

@mcp.tool()
def search_docs(query: str) -> str:
    return f"result:{query}"

if __name__ == "__main__":
    mcp.run(transport=transport)
""".lstrip(),
        encoding="utf-8",
    )


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_tcp_port(port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise TimeoutError(f"MCP streamable HTTP server did not listen on port {port}")
