from l1_support_agent.agent.runtime import (
    AgentOutcome,
    AgentOutcomeKind,
    run_support_agent,
)
from l1_support_agent.domain import Case, Events, transition
from l1_support_agent.llm.client import LLMClient
from l1_support_agent.mcp.client import MCPClient

_OUTCOME_EVENTS = {
    AgentOutcomeKind.RESOLVED: Events.CASE_RESOLVED,
    AgentOutcomeKind.ESCALATED_L2: Events.L2_ESCALATED,
}


async def process_case(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> AgentOutcome:
    """Run the bounded agent and apply its successful lifecycle event."""

    outcome = await run_support_agent(
        case,
        llm,
        mcp_client,
        max_steps=max_steps,
    )
    case.state = transition(case.state, _OUTCOME_EVENTS[outcome.kind])
    return outcome
