import os
from pathlib import Path
from typing import TypedDict

from mcp.server import MCPServer

from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database

DATABASE_PATH = Path(
    os.environ.get(
        "SUPPORT_DB_PATH",
        "support.db",
    )
)


class KnowledgeArticlePayload(TypedDict):
    id: str
    title: str
    content: str
    category: str | None


class KnowledgeSearchPayload(TypedDict):
    articles: list[KnowledgeArticlePayload]


mcp = MCPServer("l1-support-agent")


@mcp.tool()
def search_kb(
    query: str,
    limit: int = 5,
) -> KnowledgeSearchPayload:
    """Search the L1 support knowledge base.

    Use a short query containing the essential symptoms or error message.
    """

    connection = connect_database(DATABASE_PATH)

    try:
        articles = KnowledgeRepository(connection).search(
            query,
            limit=limit,
        )

        return {
            "articles": [
                {
                    "id": article.id,
                    "title": article.title,
                    "content": article.content,
                    "category": article.category,
                }
                for article in articles
            ]
        }
    finally:
        connection.close()


if __name__ == "__main__":
    mcp.run()
