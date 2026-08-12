import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from l1_support_agent.domain import Ticket
from l1_support_agent.integrations.tickets.mockapi import (
    MockApiTicketClient,
    parse_ticket,
)


@pytest.fixture
def mockapi_ticket_payload() -> dict[str, object]:
    return {
        "id": "21",
        "user": "Андрей Морозов",
        "title": "Не сохраняются данные",
        "description": "В отчете за прошлый месяц не сходятся суммы.",
        "category": "Ошибки в работе ПО",
        "priority": "Критический",
        "status": "Новая",
        "createdAt": "2026-08-11T07:26:19.190Z",
    }


def test_parse_ticket_maps_mockapi_payload_to_domain_ticket(
    mockapi_ticket_payload: dict[str, object],
) -> None:
    ticket = parse_ticket(mockapi_ticket_payload)

    assert ticket == Ticket(
        source="mockapi",
        source_id="21",
        user="Андрей Морозов",
        title="Не сохраняются данные",
        description="В отчете за прошлый месяц не сходятся суммы.",
        metadata={
            "category": "Ошибки в работе ПО",
            "priority": "Критический",
            "status": "Новая",
            "createdAt": "2026-08-11T07:26:19.190Z",
        },
    )


def test_parse_ticket_does_not_duplicate_generic_fields_in_metadata(
    mockapi_ticket_payload: dict[str, object],
) -> None:
    ticket = parse_ticket(mockapi_ticket_payload)

    assert {"id", "user", "title", "description"}.isdisjoint(ticket.metadata)


def test_get_ticket_performs_expected_request_and_returns_ticket(
    mockapi_ticket_payload: dict[str, object],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=mockapi_ticket_payload)

    async def exercise() -> Ticket:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = MockApiTicketClient(
                http_client,
                tickets_url="https://mockapi.test/tickets",
            )
            return await client.get_ticket("21")

    ticket = asyncio.run(exercise())

    assert [(request.method, str(request.url)) for request in requests] == [
        ("GET", "https://mockapi.test/tickets/21")
    ]
    assert ticket == parse_ticket(mockapi_ticket_payload)


def test_list_tickets_parses_multiple_tickets(
    mockapi_ticket_payload: dict[str, object],
) -> None:
    second_payload = {
        **mockapi_ticket_payload,
        "id": "22",
        "user": "Ирина Морозова",
        "title": "Ошибка при авторизации",
    }
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[mockapi_ticket_payload, second_payload])

    async def exercise() -> list[Ticket]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = MockApiTicketClient(
                http_client,
                tickets_url="https://mockapi.test/tickets",
            )
            return await client.list_tickets()

    tickets = asyncio.run(exercise())

    assert [(request.method, str(request.url)) for request in requests] == [
        ("GET", "https://mockapi.test/tickets")
    ]
    assert tickets == [parse_ticket(mockapi_ticket_payload), parse_ticket(second_payload)]


@pytest.mark.parametrize(
    ("client_call", "response_payload", "error_message"),
    [
        (lambda client: client.get_ticket("21"), [], "response must be an object"),
        (lambda client: client.list_tickets(), {}, "response must be a list"),
        (lambda client: client.list_tickets(), [[]], "ticket must be an object"),
    ],
)
def test_client_rejects_invalid_response_shapes(
    client_call: Callable[[MockApiTicketClient], Awaitable[object]],
    response_payload: object,
    error_message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    async def exercise() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = MockApiTicketClient(
                http_client,
                tickets_url="https://mockapi.test/tickets",
            )
            return await client_call(client)

    with pytest.raises(ValueError, match=error_message):
        asyncio.run(exercise())


@pytest.mark.parametrize("method_name", ["get_ticket", "list_tickets"])
def test_client_propagates_http_status_errors(method_name: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async def exercise() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = MockApiTicketClient(
                http_client,
                tickets_url="https://mockapi.test/tickets",
            )
            if method_name == "get_ticket":
                return await client.get_ticket("21")
            return await client.list_tickets()

    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(exercise())

    assert error.value.response.status_code == 503
