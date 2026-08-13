from collections.abc import Mapping

from l1_support_agent.domain import Ticket
from l1_support_agent.mcp.client import MCPClient


class MCPTicketPayloadError(ValueError):
    """An MCP ticket capability returned malformed structured content."""


def _parse_ticket(payload: object) -> Ticket:
    if not isinstance(payload, Mapping):
        raise MCPTicketPayloadError("MCP ticket must be an object")

    string_fields = ("source", "source_id", "user", "title", "description")
    values: dict[str, str] = {}
    for field in string_fields:
        value = payload.get(field)
        if not isinstance(value, str):
            raise MCPTicketPayloadError(
                f"MCP ticket field {field!r} must be a string"
            )
        values[field] = value

    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise MCPTicketPayloadError("MCP ticket metadata must be an object")

    return Ticket(
        source=values["source"],
        source_id=values["source_id"],
        user=values["user"],
        title=values["title"],
        description=values["description"],
        metadata=dict(metadata),
    )


class MCPTicketClient:
    """Domain ticket adapter over generic MCP ticket capabilities."""

    def __init__(self, mcp_client: MCPClient) -> None:
        self._mcp_client = mcp_client

    async def get_ticket(self, ticket_id: str) -> Ticket:
        result = await self._mcp_client.call_tool(
            "get_ticket",
            {"ticket_id": ticket_id},
        )
        if not isinstance(result, Mapping):
            raise MCPTicketPayloadError("get_ticket result must be an object")
        if "ticket" not in result:
            raise MCPTicketPayloadError("get_ticket result must contain ticket")
        return _parse_ticket(result["ticket"])

    async def list_tickets(self) -> list[Ticket]:
        result = await self._mcp_client.call_tool("list_tickets", {})
        if not isinstance(result, Mapping):
            raise MCPTicketPayloadError("list_tickets result must be an object")

        tickets = result.get("tickets")
        if not isinstance(tickets, list):
            raise MCPTicketPayloadError(
                "list_tickets result must contain a tickets list"
            )
        return [_parse_ticket(ticket) for ticket in tickets]
