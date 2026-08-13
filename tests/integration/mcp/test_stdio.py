import asyncio

import pytest

from l1_support_agent.agent.runtime import AgentRuntimeError
from l1_support_agent.interfaces import RuntimeConfig, build_mcp_server_parameters
from l1_support_agent.mcp.client import connect_stdio_mcp
from l1_support_agent.persistence.database import connect_database


def test_real_stdio_server_discovers_company_capabilities(tmp_path) -> None:
    database_path = tmp_path / "stdio.db"
    parameters = build_mcp_server_parameters(
        RuntimeConfig(database_path=database_path)
    )

    async def discover() -> set[str]:
        async with connect_stdio_mcp(parameters) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(discover()) == {
        "list_tickets",
        "get_ticket",
        "search_kb",
        "escalate_l2",
        "create_github_issue",
    }
    assert database_path.is_file()
    connection = connect_database(database_path)
    try:
        connection.execute("SELECT 1 FROM knowledge_articles LIMIT 1")
    finally:
        connection.close()


def test_consumer_exception_survives_real_stdio_cleanup(tmp_path) -> None:
    parameters = build_mcp_server_parameters(
        RuntimeConfig(database_path=tmp_path / "consumer-error.db")
    )
    expected = AgentRuntimeError("Knowledge base contains no adequate solution")

    async def fail_inside_context() -> None:
        async with connect_stdio_mcp(parameters):
            raise expected

    with pytest.raises(AgentRuntimeError) as raised:
        asyncio.run(fail_inside_context())

    assert raised.value is expected


def test_real_stdio_mock_write_capabilities_are_safe_without_credentials(
    tmp_path,
) -> None:
    parameters = build_mcp_server_parameters(
        RuntimeConfig(database_path=tmp_path / "mock-writes.db"),
        environment={"SUPPORT_SIDE_EFFECT_MODE": "mock"},
    )

    async def call_mock_writes() -> tuple[object, object]:
        async with connect_stdio_mcp(parameters) as client:
            telegram = await client.call_tool(
                "escalate_l2",
                {
                    "summary": "Office network unavailable",
                    "ticket_reference": "mockapi:2",
                },
            )
            github = await client.call_tool(
                "create_github_issue",
                {
                    "title": "Login returns HTTP 500",
                    "technical_context": "Valid login triggers a server error.",
                    "ticket_description": "User cannot sign in.",
                    "errors_logs": "HTTP 500",
                    "ticket_reference": "mockapi:17",
                },
            )
            return telegram, github

    telegram, github = asyncio.run(call_mock_writes())

    assert isinstance(telegram, dict)
    assert isinstance(telegram.get("message_id"), int)
    assert telegram["message_id"] > 0
    assert isinstance(github, dict)
    assert str(github.get("issue_url", "")).startswith(
        "https://mock.invalid/github/issues/"
    )
