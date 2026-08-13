import asyncio

import pytest

from l1_support_agent.agent.runtime import (
    AgentStepLimitError,
    run_resolution_agent,
)
from l1_support_agent.application.resolve_case import resolve_case
from l1_support_agent.application.tool_policy import ToolNotAllowedError
from l1_support_agent.domain import Case, CaseState, Ticket
from l1_support_agent.llm.client import (
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)

SEARCH_KB = ToolDefinition(
    name="search_kb",
    description="Search support instructions.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
CREATE_ISSUE = ToolDefinition(
    name="create_github_issue",
    description="Create a development issue.",
    input_schema={"type": "object"},
)


@pytest.fixture
def processing_case() -> Case:
    case = Case.from_ticket(
        Ticket(
            source="mockapi",
            source_id="1",
            user="alice",
            title="Computer beeps and does not boot",
            description="The computer emits three beeps during startup.",
        )
    )
    case.state = CaseState.PROCESSING
    case.category = "hardware"
    case.priority = "high"
    return case


class FakeMCPClient:
    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self.tools = tools or [SEARCH_KB]
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> list[ToolDefinition]:
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        self.calls.append((name, arguments))
        return {
            "articles": [
                {
                    "title": "POST beep codes",
                    "content": "Reseat the RAM and retry startup.",
                }
            ]
        }


class ScriptedLLMClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[list[LLMMessage], list[ToolDefinition] | None]] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self.calls.append((list(messages), tools))
        return next(self._responses)


def kb_then_answer_llm() -> ScriptedLLMClient:
    return ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        name="search_kb",
                        arguments={"query": "computer three beeps startup"},
                    ),
                ),
            ),
            LLMResponse(
                content="Power off the computer, reseat the RAM, and retry startup."
            ),
        ]
    )


def test_runtime_filters_tools_executes_search_and_feeds_result_to_llm(
    processing_case: Case,
) -> None:
    llm = kb_then_answer_llm()
    mcp_client = FakeMCPClient([SEARCH_KB, CREATE_ISSUE])

    answer = asyncio.run(
        run_resolution_agent(processing_case, llm, mcp_client)
    )

    assert answer.startswith("Power off the computer")
    assert mcp_client.calls == [
        ("search_kb", {"query": "computer three beeps startup"})
    ]
    assert [tool.name for tool in llm.calls[0][1] or []] == ["search_kb"]
    assert [tool.name for tool in llm.calls[1][1] or []] == [
        "create_github_issue"
    ]

    second_turn_messages = llm.calls[1][0]
    assert second_turn_messages[-1].tool_name == "search_kb"
    assert "POST beep codes" in second_turn_messages[-1].content


def test_runtime_rejects_forbidden_call_before_mcp_execution(
    processing_case: Case,
) -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        name="create_github_issue",
                        arguments={"title": "Boot failure"},
                    ),
                ),
            )
        ]
    )
    mcp_client = FakeMCPClient([SEARCH_KB, CREATE_ISSUE])

    with pytest.raises(ToolNotAllowedError, match="create_github_issue"):
        asyncio.run(run_resolution_agent(processing_case, llm, mcp_client))

    assert mcp_client.calls == []


def test_runtime_stops_at_max_steps(processing_case: Case) -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        name="search_kb",
                        arguments={"query": "beep"},
                    ),
                ),
            )
        ]
    )

    with pytest.raises(AgentStepLimitError, match="1-step limit"):
        asyncio.run(
            run_resolution_agent(
                processing_case,
                llm,
                FakeMCPClient(),
                max_steps=1,
            )
        )


def test_successful_scenario_transitions_case_to_resolved(
    processing_case: Case,
) -> None:
    answer = asyncio.run(
        resolve_case(
            processing_case,
            kb_then_answer_llm(),
            FakeMCPClient(),
        )
    )

    assert answer.startswith("Power off the computer")
    assert processing_case.state is CaseState.RESOLVED
