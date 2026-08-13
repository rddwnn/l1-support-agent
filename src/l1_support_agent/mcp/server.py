import os
from pathlib import Path
from typing import TypedDict

import httpx
from mcp.server import MCPServer

from l1_support_agent.domain import Ticket
from l1_support_agent.integrations.github import GitHubClient, GitHubConfig
from l1_support_agent.integrations.telegram import TelegramClient, TelegramConfig
from l1_support_agent.integrations.tickets.mockapi import MockApiTicketClient
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database, init_database

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


class TicketPayload(TypedDict):
    source: str
    source_id: str
    user: str
    title: str
    description: str
    metadata: dict[str, object]


class GetTicketPayload(TypedDict):
    ticket: TicketPayload


class ListTicketsPayload(TypedDict):
    tickets: list[TicketPayload]


class TelegramEscalationPayload(TypedDict):
    message_id: int


class GitHubIssuePayload(TypedDict):
    issue_url: str


mcp = MCPServer("l1-support-agent")


def _serialize_ticket(ticket: Ticket) -> TicketPayload:
    return {
        "source": ticket.source,
        "source_id": ticket.source_id,
        "user": ticket.user,
        "title": ticket.title,
        "description": ticket.description,
        "metadata": dict(ticket.metadata),
    }


@mcp.tool()
async def get_ticket(ticket_id: str) -> GetTicketPayload:
    """Fetch one support ticket from the configured read-only ticket source."""

    async with httpx.AsyncClient() as http_client:
        ticket = await MockApiTicketClient(http_client).get_ticket(ticket_id)
    return {"ticket": _serialize_ticket(ticket)}


@mcp.tool()
async def list_tickets() -> ListTicketsPayload:
    """List support tickets from the configured read-only ticket source."""

    async with httpx.AsyncClient() as http_client:
        tickets = await MockApiTicketClient(http_client).list_tickets()
    return {"tickets": [_serialize_ticket(ticket) for ticket in tickets]}


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


@mcp.tool()
async def create_github_issue(
    title: str,
    technical_context: str,
    ticket_description: str,
    errors_logs: str,
    ticket_reference: str,
) -> GitHubIssuePayload:
    """Create a development issue for a software defect found by L1 support."""

    async with httpx.AsyncClient() as http_client:
        issue_url = await GitHubClient(
            http_client,
            GitHubConfig.from_env(),
        ).create_support_issue(
            title=title,
            technical_context=technical_context,
            ticket_description=ticket_description,
            errors_logs=errors_logs,
            ticket_reference=ticket_reference,
        )

    return {"issue_url": issue_url}


def main() -> None:
    """Initialize local storage and run the reusable stdio capability server."""

    init_database(DATABASE_PATH)
    mcp.run()


if __name__ == "__main__":
    main()
