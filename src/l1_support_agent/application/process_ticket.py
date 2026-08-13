from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from l1_support_agent.application.process_case import process_case
from l1_support_agent.application.triage_case import triage_case
from l1_support_agent.domain import Case, CaseState, Ticket
from l1_support_agent.llm.client import LLMClient
from l1_support_agent.mcp.client import MCPClient
from l1_support_agent.persistence.repositories import CaseRepository, TicketRepository


class TicketClient(Protocol):
    async def get_ticket(self, ticket_id: str) -> Ticket: ...


@dataclass(frozen=True, slots=True)
class TicketProcessingResult:
    case_id: UUID
    source_ticket_id: str
    final_state: CaseState
    category: str | None
    priority: str | None
    outcome_message: str | None


_TERMINAL_STATES = frozenset(
    {
        CaseState.RESOLVED,
        CaseState.ESCALATED_L2,
        CaseState.ESCALATED_DEVELOPMENT,
    }
)


def _result(case: Case, outcome_message: str | None) -> TicketProcessingResult:
    return TicketProcessingResult(
        case_id=case.id,
        source_ticket_id=case.ticket.source_id,
        final_state=case.state,
        category=case.category,
        priority=case.priority,
        outcome_message=outcome_message,
    )


async def process_ticket_by_id(
    ticket_id: str,
    ticket_client: TicketClient,
    ticket_repository: TicketRepository,
    case_repository: CaseRepository,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> TicketProcessingResult:
    """Fetch and process one source ticket through its persisted Case lifecycle."""

    ticket = await ticket_client.get_ticket(ticket_id)
    ticket_repository.save(ticket)

    new_case = Case.from_ticket(ticket)
    case = case_repository.get(new_case.id)
    if case is None:
        case = new_case
        case_repository.save(case)

    if case.state in _TERMINAL_STATES:
        return _result(case, outcome_message=None)

    if case.state is CaseState.NEW:
        await triage_case(case, llm)
        case_repository.save(case)

    outcome = await process_case(
        case,
        llm,
        mcp_client,
        max_steps=max_steps,
    )
    case_repository.save(case)

    return _result(case, outcome.message)
