from l1_support_agent.application.process_case import process_case
from l1_support_agent.domain import Case
from l1_support_agent.llm.client import LLMClient
from l1_support_agent.mcp.client import MCPClient


async def resolve_case(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> str:
    """Run the support flow and return its user-facing outcome message."""

    outcome = await process_case(
        case,
        llm,
        mcp_client,
        max_steps=max_steps,
    )
    return outcome.message
