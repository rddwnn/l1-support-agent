from dataclasses import dataclass
from uuid import UUID

from states import CaseState


@dataclass
class Case:
    id: UUID
    source_ticket_id: str
    state: CaseState
    category: str | None = None
    priority: str | None = None
