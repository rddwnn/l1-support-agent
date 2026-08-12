from l1_support_agent.domain import Case
from l1_support_agent.domain import CaseState
from l1_support_agent.domain import Ticket


def test_case_creation():
    ticket = Ticket(
        source="mockapi",
        source_id="123",
        user="test_user",
        title="Test ticket",
        description="Something is broken",
    )

    case = Case.from_ticket(ticket)

    assert case.ticket == ticket
    assert case.state == CaseState.NEW
    assert case.category is None
    assert case.priority is None