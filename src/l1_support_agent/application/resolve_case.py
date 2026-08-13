from l1_support_agent.agent.runtime import run_resolution_agent
from l1_support_agent.domain import Case, Events, transition
from l1_support_agent.llm.client import LLMClient
from l1_support_agent.mcp.client import MCPClient


async def resolve_case(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> str:
    """Run Scenario A and apply the legal resolved lifecycle transition."""

    answer = await run_resolution_agent(
        case,
        llm,
        mcp_client,
        max_steps=max_steps,
    )
    case.state = transition(case.state, Events.CASE_RESOLVED)
    return answer
