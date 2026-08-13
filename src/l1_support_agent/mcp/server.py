import os
from pathlib import Path

from mcp.server import MCPServer

from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database

DATABASE_PATH = Path(
    os.environ.get(
        "SUPPORT_DB_PATH",
        "support.db",
    )
)

mcp = MCPServer("l1-support-agent")


@mcp.tool()
def search_kb(
    query: str,
    limit: int = 5,
) -> list[KnowledgeArticle]:
    """Search the L1 support knowledge base for relevant instructions."""
    connection = connect_database(DATABASE_PATH)

    try:
        repository = KnowledgeRepository(connection)

        return repository.search(
            query,
            limit=limit,
        )
    finally:
        connection.close()


if __name__ == "__main__":
    mcp.run()