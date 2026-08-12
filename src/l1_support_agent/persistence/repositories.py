import json
import sqlite3
from uuid import UUID

from l1_support_agent.domain import Case, CaseState, Ticket


class TicketRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, ticket: Ticket) -> None:
        self._connection.execute(
            """
            INSERT INTO tickets (
                source,
                source_id,
                user,
                title,
                description,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id) DO NOTHING
            """,
            (
                ticket.source,
                ticket.source_id,
                ticket.user,
                ticket.title,
                ticket.description,
                json.dumps(ticket.metadata),
            ),
        )

        self._connection.commit()

    def get(
        self,
        source: str,
        source_id: str,
    ) -> Ticket | None:
        row = self._connection.execute(
            """
            SELECT
                source,
                source_id,
                user,
                title,
                description,
                metadata
            FROM tickets
            WHERE source = ?
            AND source_id = ?
            """,
            (source, source_id),
        ).fetchone()

        if row is None:
            return None

        return Ticket(
            source=row["source"],
            source_id=row["source_id"],
            user=row["user"],
            title=row["title"],
            description=row["description"],
            metadata=json.loads(row["metadata"]),
        )


class CaseRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, case: Case) -> None:
        self._connection.execute(
            """
            INSERT INTO cases (
                id,
                ticket_source,
                ticket_source_id,
                state,
                category,
                priority
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state = excluded.state,
                category = excluded.category,
                priority = excluded.priority
            """,
            (
                str(case.id),
                case.ticket.source,
                case.ticket.source_id,
                case.state.value,
                case.category,
                case.priority,
            ),
        )

        self._connection.commit()

    def get(self, case_id: UUID) -> Case | None:
        row = self._connection.execute(
            """
            SELECT
                c.id,
                c.state,
                c.category,
                c.priority,

                t.source,
                t.source_id,
                t.user,
                t.title,
                t.description,
                t.metadata

            FROM cases AS c
            JOIN tickets AS t
                ON c.ticket_source = t.source
                AND c.ticket_source_id = t.source_id

            WHERE c.id = ?
            """,
            (str(case_id),),
        ).fetchone()

        if row is None:
            return None

        ticket = Ticket(
            source=row["source"],
            source_id=row["source_id"],
            user=row["user"],
            title=row["title"],
            description=row["description"],
            metadata=json.loads(row["metadata"])
        )

        return Case(
            id=UUID(row["id"]),
            ticket=ticket,
            state=CaseState(row["state"]),
            category=row["category"],
            priority=row["priority"],
        )