import json

from l1_support_agent.application.tool_policy import (
    AgentContext,
    allowed_tool_names,
    ensure_tool_allowed,
)
from l1_support_agent.domain import Case
from l1_support_agent.llm.client import (
    LLMClient,
    LLMMessage,
    MessageRole,
)
from l1_support_agent.mcp.client import MCPClient

SYSTEM_PROMPT = (
    "You are an autonomous L1 support agent. Use available tools when needed and "
    "rely on their results instead of inventing instructions. After finding adequate "
    "instructions, give a concise user-facing answer. Do not claim an action was "
    "performed unless a tool result establishes it."
)


class AgentRuntimeError(RuntimeError):
    """The bounded agent run could not produce a valid final answer."""


class AgentStepLimitError(AgentRuntimeError):
    """The agent exceeded its configured maximum number of steps."""


async def run_resolution_agent(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> str:
    """Resolve a triaged case through the bounded known-KB scenario."""

    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    context = AgentContext()
    discovered_tools = await mcp_client.list_tools()
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(
                {
                    "title": case.ticket.title,
                    "description": case.ticket.description,
                    "category": case.category,
                    "priority": case.priority,
                },
                ensure_ascii=False,
            ),
        ),
    ]

    for _ in range(max_steps):
        allowed_names = allowed_tool_names(case, context)
        visible_tools = [
            tool for tool in discovered_tools if tool.name in allowed_names
        ]
        response = await llm.chat(messages, tools=visible_tools)

        if not response.tool_calls:
            if not context.kb_searched:
                raise AgentRuntimeError(
                    "Agent returned a final answer before searching the knowledge base"
                )
            if not response.content.strip():
                raise AgentRuntimeError("Agent returned an empty final answer")
            return response.content

        messages.append(
            LLMMessage(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            )
        )

        for tool_call in response.tool_calls:
            ensure_tool_allowed(tool_call.name, case, context)
            result = await mcp_client.call_tool(
                tool_call.name,
                tool_call.arguments,
            )
            messages.append(
                LLMMessage(
                    role=MessageRole.TOOL,
                    content=json.dumps(result, ensure_ascii=False),
                    tool_name=tool_call.name,
                )
            )

            if tool_call.name == "search_kb":
                context = AgentContext(kb_searched=True)

    raise AgentStepLimitError(f"Agent exceeded the {max_steps}-step limit")
