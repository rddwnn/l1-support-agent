import os
from pathlib import Path
from typing import TypedDict

import httpx
from mcp.server import MCPServer

from l1_support_agent.integrations.telegram import TelegramClient, TelegramConfig
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


class TelegramEscalationPayload(TypedDict):
    message_id: int


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


@mcp.tool()
async def escalate_l2(
    summary: str,
    ticket_reference: str,
) -> TelegramEscalationPayload:
    """Escalate an infrastructure problem to the L2 support Telegram chat."""

    async with httpx.AsyncClient() as http_client:
        message_id = await TelegramClient(
            http_client,
            TelegramConfig.from_env(),
        ).send_l2_escalation(summary, ticket_reference)

    return {"message_id": message_id}


if __name__ == "__main__":
    mcp.run()
