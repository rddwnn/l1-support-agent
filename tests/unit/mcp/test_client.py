import asyncio
from typing import cast

from mcp import ClientSession
from mcp.types import CallToolResult, ListToolsResult
from mcp.types import Tool as MCPTool

from l1_support_agent.llm.client import ToolDefinition
from l1_support_agent.mcp.client import SessionMCPClient


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                MCPTool(
                    name="search_kb",
                    description="Search support instructions.",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                )
            ]
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[],
            structuredContent={"articles": [{"title": "Reset password"}]},
        )


def test_list_tools_converts_mcp_metadata_to_tool_definitions() -> None:
    async def exercise() -> list[ToolDefinition]:
        session = cast(ClientSession, FakeSession())
        return await SessionMCPClient(session).list_tools()

    tools = asyncio.run(exercise())

    assert tools == [
        ToolDefinition(
            name="search_kb",
            description="Search support instructions.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
    ]


def test_call_tool_returns_normalized_structured_content() -> None:
    session = FakeSession()

    async def exercise() -> object:
        client = SessionMCPClient(cast(ClientSession, session))
        return await client.call_tool("search_kb", {"query": "password"})

    result = asyncio.run(exercise())

    assert result == {"articles": [{"title": "Reset password"}]}
    assert session.calls == [("search_kb", {"query": "password"})]
