import sqlite3

import pytest

from l1_support_agent.domain import Case, CaseState, Ticket
from l1_support_agent.persistence.database import (
    connect_database,
    init_database,
)
from l1_support_agent.persistence.repositories import (
    CaseRepository,
    TicketRepository,
)


@pytest.fixture
def connection(tmp_path):
    database_path = tmp_path / "test.db"

    init_database(database_path)

    connection = connect_database(database_path)

    yield connection

    connection.close()


@pytest.fixture
def ticket():
    return Ticket(
        source="mockapi",
        source_id="42",
        user="Rodion",
        title="VPN problem",
        description="VPN does not connect",
        metadata={
            "category": "network",
            "priority": "high",
        },
    )


def test_ticket_round_trip(connection, ticket):
    repository = TicketRepository(connection)

    repository.save(ticket)

    loaded_ticket = repository.get(
        ticket.source,
        ticket.source_id,
    )

    assert loaded_ticket == ticket


def test_case_round_trip(connection, ticket):
    ticket_repository = TicketRepository(connection)
    case_repository = CaseRepository(connection)

    ticket_repository.save(ticket)

    case = Case.from_ticket(ticket)
    case_repository.save(case)

    loaded_case = case_repository.get(case.id)

    assert loaded_case == case


def test_case_save_updates_state_category_and_priority(
    connection,
    ticket,
):
    ticket_repository = TicketRepository(connection)
    case_repository = CaseRepository(connection)

    ticket_repository.save(ticket)

    case = Case.from_ticket(ticket)
    case_repository.save(case)

    case.state = CaseState.PROCESSING
    case.category = "infrastructure"
    case.priority = "high"

    case_repository.save(case)

    loaded_case = case_repository.get(case.id)

    assert loaded_case is not None
    assert loaded_case.state == CaseState.PROCESSING
    assert loaded_case.category == "infrastructure"
    assert loaded_case.priority == "high"


def test_case_cannot_be_saved_without_ticket(
    connection,
    ticket,
):
    repository = CaseRepository(connection)

    case = Case.from_ticket(ticket)

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(case)

