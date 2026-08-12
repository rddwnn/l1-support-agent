import json
import sqlite3


from l1_support_agent.domain import Ticket


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
    