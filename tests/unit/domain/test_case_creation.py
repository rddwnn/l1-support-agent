from l1_support_agent.domain import Case
from l1_support_agent.domain import CaseState

from uuid import uuid4

def test_case_creation():
    case = Case(
        id=uuid4(),
        source_ticket_id='21',
        state=CaseState.NEW
    )
    assert case.source_ticket_id == '21'
    assert case.state == CaseState.NEW
    assert case.category is None
    assert case.priority is None 
