import asyncio

import pytest

from l1_support_agent.domain import Ticket
from l1_support_agent.integrations.tickets.mcp import (
    MCPTicketClient,
    MCPTicketPayloadError,
)
from l1_support_agent.llm.client import ToolDefinition

TICKET_PAYLOAD: dict[str, object] = {
    "source": "mockapi",
    "source_id": "21",
    "user": "alice",
    "title": "Application fails to save",
    "description": "Saving a report returns HTTP 500.",
    "metadata": {"priority": "high", "logs": "HTTP 500"},
}


class FakeMCPClient:
    def __init__(self, results: list[object]) -> None:
        self._results = iter(results)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> list[ToolDefinition]:
        return []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        self.calls.append((name, arguments))
        return next(self._results)


def test_get_ticket_calls_mcp_and_converts_domain_ticket() -> None:
    mcp = FakeMCPClient([{"ticket": TICKET_PAYLOAD}])
    client = MCPTicketClient(mcp)

    ticket = asyncio.run(client.get_ticket("21"))

    assert ticket == Ticket(
        source="mockapi",
        source_id="21",
        user="alice",
        title="Application fails to save",
        description="Saving a report returns HTTP 500.",
        metadata={"priority": "high", "logs": "HTTP 500"},
    )
    assert mcp.calls == [("get_ticket", {"ticket_id": "21"})]


def test_list_tickets_calls_mcp_and_converts_items() -> None:
    second = {**TICKET_PAYLOAD, "source_id": "22", "user": "bob"}
    mcp = FakeMCPClient([{"tickets": [TICKET_PAYLOAD, second]}])
    client = MCPTicketClient(mcp)

    tickets = asyncio.run(client.list_tickets())

    assert [ticket.source_id for ticket in tickets] == ["21", "22"]
    assert mcp.calls == [("list_tickets", {})]


@pytest.mark.parametrize(
    "result",
    [
        [],
        {},
        {"ticket": []},
        {"ticket": {**TICKET_PAYLOAD, "metadata": []}},
        {"ticket": {**TICKET_PAYLOAD, "title": 500}},
    ],
)
def test_get_ticket_rejects_malformed_mcp_content(result: object) -> None:
    client = MCPTicketClient(FakeMCPClient([result]))

    with pytest.raises(MCPTicketPayloadError):
        asyncio.run(client.get_ticket("21"))
