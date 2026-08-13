from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from l1_support_agent.llm.client import ToolDefinition


class MCPClient(Protocol):
    async def list_tools(self) -> list[ToolDefinition]: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object: ...


class MCPToolCallError(RuntimeError):
    """An MCP tool reported an execution error."""


class SessionMCPClient:
    """Provider-neutral adapter over an initialized MCP client session."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> list[ToolDefinition]:
        result = await self._session.list_tools()
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(tool.input_schema),
            )
            for tool in result.tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        result = await self._session.call_tool(name, arguments)
        if not isinstance(result, CallToolResult):
            raise TypeError("MCP tool call must return a completed result")
        if result.is_error:
            raise MCPToolCallError(f"MCP tool {name!r} reported an error")
        if result.structured_content is not None:
            return result.structured_content

        return [
            content.model_dump(mode="json", by_alias=True, exclude_none=True)
            for content in result.content
        ]


@asynccontextmanager
async def connect_stdio_mcp(
    server: StdioServerParameters,
) -> AsyncIterator[SessionMCPClient]:
    """Start an MCP stdio server and yield an initialized client adapter."""

    pending_error: Exception | None = None
    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        try:
            yield SessionMCPClient(session)
        except Exception as error:  # noqa: BLE001 - preserve consumer exception
            pending_error = error

    if pending_error is not None:
        raise pending_error
