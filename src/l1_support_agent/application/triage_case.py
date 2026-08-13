from l1_support_agent.agent.triage import (
    TriageResult,
    triage_ticket,
)
from l1_support_agent.domain import (
    Case,
    Events,
    transition,
)
from l1_support_agent.llm.client import LLMClient


async def triage_case(
    case: Case,
    llm: LLMClient,
) -> TriageResult:
    case.state = transition(
        case.state,
        Events.PROCESSING_STARTED,
    )

    result = await triage_ticket(
        case.ticket,
        llm,
    )

    case.category = result.category
    case.priority = result.priority

    return result
