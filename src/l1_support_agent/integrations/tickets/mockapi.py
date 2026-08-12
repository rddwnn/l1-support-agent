from collections.abc import Mapping

import httpx

from l1_support_agent.domain import Ticket


TICKETS_URL = "https://6a7ad74c8c69b3eb4a179621.mockapi.io/tickets/tickets"


def parse_ticket(payload: Mapping[str, object]) -> Ticket:
    ticket_fields = {
        "id",
        "user",
        "title",
        "description",
    }

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in ticket_fields
    }

    return Ticket(
        source="mockapi",
        source_id=str(payload["id"]),
        user=str(payload["user"]),
        title=str(payload["title"]),
        description=str(payload["description"]),
        metadata=metadata,
    )


class MockApiTicketClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        tickets_url: str = TICKETS_URL,
    ) -> None:
        self._client = client
        self._tickets_url = tickets_url.rstrip("/")

    async def get_ticket(self, ticket_id: str) -> Ticket:
        response = await self._client.get(
            f"{self._tickets_url}/{ticket_id}"
        )
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(
                "MockAPI ticket response must be an object"
            )

        return parse_ticket(payload)

    async def list_tickets(self) -> list[Ticket]:
        response = await self._client.get(self._tickets_url)
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError(
                "MockAPI tickets response must be a list"
            )

        tickets = []

        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(
                    "MockAPI ticket must be an object"
                )

            tickets.append(parse_ticket(item))

        return tickets