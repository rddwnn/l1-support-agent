import asyncio

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
