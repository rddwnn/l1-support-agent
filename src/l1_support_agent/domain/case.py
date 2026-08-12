from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from .states import CaseState
from .ticket import Ticket


@dataclass
class Case:
    id: UUID
    ticket: Ticket
    state: CaseState = CaseState.NEW
    category: str | None = None
    priority: str | None = None


    @classmethod
    def from_ticket(cls, ticket: Ticket) -> "Case":
        return cls(
            id=uuid5(
                NAMESPACE_URL,
                f"{ticket.source}:{ticket.source_id}"
            ),
            ticket=ticket
        )

    