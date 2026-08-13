import asyncio
from pathlib import Path
from typing import ClassVar

import pytest

from l1_support_agent.domain import Ticket
from l1_support_agent.integrations.github import GitHubError
from l1_support_agent.integrations.side_effects import SideEffectModeError
from l1_support_agent.integrations.telegram import TelegramError
from l1_support_agent.mcp import server
from l1_support_agent.persistence.database import connect_database


class FakeTicketSource:
    tickets: ClassVar[list[Ticket]] = [
        Ticket(
            source="mockapi",
            source_id="21",
            user="alice",
            title="Application fails to save",
            description="Saving a report returns HTTP 500.",
            metadata={"priority": "high", "logs": "HTTP 500"},
        ),
        Ticket(
            source="mockapi",
            source_id="22",
            user="bob",
            title="Office network unavailable",
            description="The gateway is unreachable.",
            metadata={"priority": "critical"},
        ),
    ]

    def __init__(self, http_client: object) -> None:
        self.http_client = http_client

    async def get_ticket(self, ticket_id: str) -> Ticket:
        assert ticket_id == "21"
        return self.tickets[0]

    async def list_tickets(self) -> list[Ticket]:
        return self.tickets


def test_server_advertises_company_capabilities() -> None:
    tools = asyncio.run(server.mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "list_tickets",
        "get_ticket",
        "search_kb",
        "escalate_l2",
        "create_github_issue",
    }


def test_get_ticket_returns_explicit_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(server, "MockApiTicketClient", FakeTicketSource)

    result = asyncio.run(server.get_ticket("21"))

    assert result == {
        "ticket": {
            "source": "mockapi",
            "source_id": "21",
            "user": "alice",
            "title": "Application fails to save",
            "description": "Saving a report returns HTTP 500.",
            "metadata": {"priority": "high", "logs": "HTTP 500"},
        }
    }


def test_list_tickets_returns_explicit_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(server, "MockApiTicketClient", FakeTicketSource)

    result = asyncio.run(server.list_tickets())

    assert result == {
        "tickets": [server._serialize_ticket(ticket) for ticket in FakeTicketSource.tickets]
    }


def test_standalone_main_initializes_fresh_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "standalone.db"
    observed_tables: set[str] = set()

    def inspect_schema() -> None:
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
            observed_tables.update(row["name"] for row in rows)
        finally:
            connection.close()

    monkeypatch.setattr(server, "DATABASE_PATH", database_path)
    monkeypatch.setattr(server.mcp, "run", inspect_schema)

    server.main()

    assert {
        "tickets",
        "cases",
        "knowledge_articles",
        "knowledge_articles_fts",
    } <= observed_tables


def test_mock_side_effect_tools_need_no_credentials_or_http_client(
    monkeypatch,
) -> None:
    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("mock side effects must not create an HTTP client")

    monkeypatch.setenv("SUPPORT_SIDE_EFFECT_MODE", "mock")
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GITHUB_TOKEN",
        "GITHUB_REPOSITORY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(server.httpx, "AsyncClient", ForbiddenHttpClient)

    telegram = asyncio.run(
        server.escalate_l2("Office network unavailable", "mockapi:2")
    )
    github = asyncio.run(
        server.create_github_issue(
            "Login returns HTTP 500",
            "Valid login triggers a server error.",
            "User cannot sign in.",
            "HTTP 500",
            "mockapi:17",
        )
    )

    assert isinstance(telegram["message_id"], int)
    assert telegram["message_id"] > 0
    assert github["issue_url"].startswith(
        "https://mock.invalid/github/issues/"
    )


@pytest.mark.parametrize(
    ("tool", "error_type"),
    [
        (
            lambda: server.escalate_l2("Network unavailable", "mockapi:2"),
            TelegramError,
        ),
        (
            lambda: server.create_github_issue(
                "Bug",
                "Context",
                "Description",
                "No logs",
                "mockapi:17",
            ),
            GitHubError,
        ),
    ],
)
def test_real_mode_preserves_credential_requirements(
    tool,
    error_type: type[Exception],
    monkeypatch,
) -> None:
    monkeypatch.setenv("SUPPORT_SIDE_EFFECT_MODE", "real")
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GITHUB_TOKEN",
        "GITHUB_REPOSITORY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(error_type, match="must be configured"):
        asyncio.run(tool())


def test_side_effect_tool_rejects_invalid_mode(monkeypatch) -> None:
    monkeypatch.setenv("SUPPORT_SIDE_EFFECT_MODE", "unsafe")

    with pytest.raises(SideEffectModeError, match="must be 'mock' or 'real'"):
        asyncio.run(server.escalate_l2("Network unavailable", "mockapi:2"))
