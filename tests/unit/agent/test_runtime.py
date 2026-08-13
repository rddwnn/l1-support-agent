import asyncio
import json

import pytest

from l1_support_agent.agent.runtime import (
    POST_KB_DECISION_SCHEMA,
    AgentRuntimeError,
    AgentStepLimitError,
    run_resolution_agent,
)
from l1_support_agent.application.process_case import process_case
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
ESCALATE_L2 = ToolDefinition(
    name="escalate_l2",
    description="Escalate an infrastructure issue to L2.",
    input_schema={"type": "object"},
)
GET_TICKET = ToolDefinition(
    name="get_ticket",
    description="Fetch a source ticket.",
    input_schema={"type": "object"},
)
LIST_TICKETS = ToolDefinition(
    name="list_tickets",
    description="List source tickets.",
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
            metadata={"url": "https://support.test/tickets/1"},
        )
    )
    case.state = CaseState.PROCESSING
    case.category = "hardware"
    case.priority = "high"
    return case


class FakeMCPClient:
    def __init__(
        self,
        tools: list[ToolDefinition] | None = None,
        *,
        search_articles: list[dict[str, object]] | None = None,
    ) -> None:
        self.tools = tools if tools is not None else [SEARCH_KB]
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.search_articles = (
            search_articles
            if search_articles is not None
            else [
                {
                    "id": "kb-post-beeps",
                    "title": "POST beep codes",
                    "content": "Reseat the RAM and retry startup.",
                }
            ]
        )

    async def list_tools(self) -> list[ToolDefinition]:
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        self.calls.append((name, arguments))
        if name == "search_kb":
            return {"articles": self.search_articles}
        if name == "escalate_l2":
            return {"message_id": 42}
        if name == "create_github_issue":
            return {"issue_url": "https://github.test/acme/app/issues/42"}
        raise AssertionError(f"Unexpected tool call: {name}")


class ScriptedLLMClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[list[LLMMessage], list[ToolDefinition] | None]] = []
        self.response_schemas: list[dict[str, object] | None] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self.calls.append((list(messages), tools))
        self.response_schemas.append(response_schema)
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
                content=(
                    '{"decision":"resolve","article_id":"kb-post-beeps",'
                    '"answer":"Power off the computer, reseat the RAM, and retry '
                    'startup.","summary":null,"issue_title":null,'
                    '"technical_context":null}'
                )
            ),
        ]
    )


def test_post_kb_schema_has_exactly_three_outcomes() -> None:
    properties = POST_KB_DECISION_SCHEMA["properties"]
    assert isinstance(properties, dict)
    decision = properties["decision"]
    assert isinstance(decision, dict)

    assert decision["enum"] == [
        "resolve",
        "escalate_l2",
        "create_github_issue",
    ]


def test_runtime_filters_tools_executes_search_and_feeds_result_to_llm(
    processing_case: Case,
) -> None:
    llm = kb_then_answer_llm()
    mcp_client = FakeMCPClient(
        [GET_TICKET, LIST_TICKETS, SEARCH_KB, CREATE_ISSUE]
    )

    answer = asyncio.run(
        run_resolution_agent(processing_case, llm, mcp_client)
    )

    assert answer.startswith("Power off the computer")
    assert mcp_client.calls == [
        ("search_kb", {"query": "computer three beeps startup"})
    ]
    assert [tool.name for tool in llm.calls[0][1] or []] == ["search_kb"]
    first_system_prompt = llm.calls[0][0][0].content
    assert "# KB Investigation" in first_system_prompt
    assert "articles as candidates, not proof" in first_system_prompt
    assert llm.calls[1][1] == []
    assert llm.response_schemas[1] == POST_KB_DECISION_SCHEMA

    second_turn_messages = llm.calls[1][0]
    assert "retrieved_articles" in second_turn_messages[-1].content
    assert "POST beep codes" in second_turn_messages[-1].content
    assert "Computer beeps" in second_turn_messages[-1].content
    post_kb_system_prompt = second_turn_messages[0].content
    assert "# L2 Escalation" in post_kb_system_prompt
    assert "# Development Escalation" in post_kb_system_prompt
    assert "`escalate_l2`" in post_kb_system_prompt
    assert "`create_github_issue`" in post_kb_system_prompt


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


@pytest.mark.parametrize(
    ("decision", "error_message"),
    [
        (
            {
                "decision": "resolve",
                "article_id": "not-returned",
                "answer": "Invented answer",
            },
            "unknown article_id",
        ),
        (
            {
                "decision": "resolve",
                "article_id": "kb-post-beeps",
                "answer": "  ",
            },
            "non-empty answer",
        ),
    ],
)
def test_runtime_rejects_invalid_resolved_decision(
    processing_case: Case,
    decision: dict[str, object],
    error_message: str,
) -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(name="search_kb", arguments={"query": "beep"}),
                ),
            ),
            LLMResponse(content=json.dumps(decision)),
        ]
    )

    with pytest.raises(AgentRuntimeError, match=error_message):
        asyncio.run(run_resolution_agent(processing_case, llm, FakeMCPClient()))


def test_runtime_rejects_invalid_post_kb_decision(
    processing_case: Case,
) -> None:
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(name="search_kb", arguments={"query": "XYZ-9999"}),
                ),
            ),
            LLMResponse(
                content=(
                    '{"decision":"defer","article_id":null,'
                    '"answer":null,"summary":null,"issue_title":null,'
                    '"technical_context":null}'
                )
            ),
        ]
    )

    with pytest.raises(AgentRuntimeError, match="invalid post-KB decision"):
        asyncio.run(resolve_case(processing_case, llm, FakeMCPClient()))

    assert processing_case.state is CaseState.PROCESSING


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


def test_l2_escalation_executes_tool_then_transitions_case(
    processing_case: Case,
) -> None:
    summary = "Office network is unavailable for all users."
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(name="search_kb", arguments={"query": "network down"}),
                ),
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "decision": "escalate_l2",
                        "article_id": None,
                        "answer": None,
                        "summary": summary,
                        "issue_title": None,
                        "technical_context": None,
                    }
                )
            ),
        ]
    )
    mcp_client = FakeMCPClient(
        [SEARCH_KB, ESCALATE_L2],
        search_articles=[],
    )

    outcome = asyncio.run(process_case(processing_case, llm, mcp_client))

    assert outcome.message == summary
    assert processing_case.state is CaseState.ESCALATED_L2
    assert "every other unresolved support request" in (
        llm.calls[1][0][0].content.lower()
    )
    assert mcp_client.calls == [
        ("search_kb", {"query": "network down"}),
        (
            "escalate_l2",
            {
                "summary": summary,
                "ticket_reference": "https://support.test/tickets/1",
            },
        ),
    ]


@pytest.mark.parametrize(
    ("category", "title", "description"),
    [
        ("hardware", "Printer jams", "The office printer repeatedly jams."),
        ("network", "No internet", "The workstation cannot reach any website."),
        ("access", "Account locked", "The user cannot access their account."),
        (
            "consultation",
            "Reporting help",
            "The user needs specialist guidance for a report.",
        ),
    ],
)
def test_unresolved_non_software_support_routes_to_l2(
    processing_case: Case,
    category: str,
    title: str,
    description: str,
) -> None:
    processing_case.category = category
    processing_case.ticket = Ticket(
        source="mockapi",
        source_id="1",
        user="alice",
        title=title,
        description=description,
    )
    summary = f"Unresolved {category} support request: {description}"
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(name="search_kb", arguments={"query": title}),
                ),
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "decision": "escalate_l2",
                        "article_id": None,
                        "answer": None,
                        "summary": summary,
                        "issue_title": None,
                        "technical_context": None,
                    }
                )
            ),
        ]
    )
    mcp_client = FakeMCPClient(
        [SEARCH_KB, ESCALATE_L2],
        search_articles=[],
    )

    outcome = asyncio.run(process_case(processing_case, llm, mcp_client))

    assert outcome.message == summary
    assert processing_case.state is CaseState.ESCALATED_L2
    assert mcp_client.calls[-1][0] == "escalate_l2"


def test_l2_transition_is_not_applied_when_tool_fails(
    processing_case: Case,
) -> None:
    class FailingMCPClient(FakeMCPClient):
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> object:
            if name == "escalate_l2":
                raise RuntimeError("Telegram unavailable")
            return await super().call_tool(name, arguments)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(ToolCall(name="search_kb", arguments={"query": "network"}),),
            ),
            LLMResponse(
                content=(
                    '{"decision":"escalate_l2","article_id":null,'
                    '"answer":null,"summary":"Network unavailable",'
                    '"issue_title":null,"technical_context":null}'
                )
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="Telegram unavailable"):
        asyncio.run(
            process_case(
                processing_case,
                llm,
                FailingMCPClient(
                    [SEARCH_KB, ESCALATE_L2],
                    search_articles=[],
                ),
            )
        )

    assert processing_case.state is CaseState.PROCESSING


@pytest.mark.parametrize(
    ("tool_result", "error_message"),
    [
        ([], "invalid content"),
        ({}, "integer message_id"),
        ({"message_id": "42"}, "integer message_id"),
        ({"message_id": True}, "integer message_id"),
    ],
)
def test_l2_transition_is_not_applied_for_malformed_tool_result(
    processing_case: Case,
    tool_result: object,
    error_message: str,
) -> None:
    class MalformedResultMCPClient(FakeMCPClient):
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> object:
            if name == "escalate_l2":
                return tool_result
            return await super().call_tool(name, arguments)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(ToolCall(name="search_kb", arguments={"query": "network"}),),
            ),
            LLMResponse(
                content=(
                    '{"decision":"escalate_l2","article_id":null,'
                    '"answer":null,"summary":"Network unavailable",'
                    '"issue_title":null,"technical_context":null}'
                )
            ),
        ]
    )

    with pytest.raises(AgentRuntimeError, match=error_message):
        asyncio.run(
            process_case(
                processing_case,
                llm,
                MalformedResultMCPClient(
                    [SEARCH_KB, ESCALATE_L2],
                    search_articles=[],
                ),
            )
        )

    assert processing_case.state is CaseState.PROCESSING


def test_software_bug_creates_issue_then_transitions_case(
    processing_case: Case,
) -> None:
    processing_case.category = "software"
    processing_case.ticket.metadata["logs"] = "HTTP 500: database timeout"
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(name="search_kb", arguments={"query": "login HTTP 500"}),
                ),
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "decision": "create_github_issue",
                        "article_id": None,
                        "answer": None,
                        "summary": None,
                        "issue_title": "Login returns HTTP 500",
                        "technical_context": (
                            "Valid credentials trigger a database timeout."
                        ),
                    }
                )
            ),
        ]
    )
    mcp_client = FakeMCPClient(
        [SEARCH_KB, CREATE_ISSUE],
        search_articles=[],
    )

    outcome = asyncio.run(process_case(processing_case, llm, mcp_client))

    assert outcome.message == "https://github.test/acme/app/issues/42"
    assert processing_case.state is CaseState.ESCALATED_DEVELOPMENT
    assert mcp_client.calls == [
        ("search_kb", {"query": "login HTTP 500"}),
        (
            "create_github_issue",
            {
                "title": "Login returns HTTP 500",
                "technical_context": (
                    "Valid credentials trigger a database timeout."
                ),
                "ticket_description": (
                    "The computer emits three beeps during startup."
                ),
                "errors_logs": '{"logs": "HTTP 500: database timeout"}',
                "ticket_reference": "https://support.test/tickets/1",
            },
        ),
    ]


def test_development_transition_is_not_applied_when_issue_creation_fails(
    processing_case: Case,
) -> None:
    class FailingMCPClient(FakeMCPClient):
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> object:
            if name == "create_github_issue":
                raise RuntimeError("GitHub unavailable")
            return await super().call_tool(name, arguments)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(ToolCall(name="search_kb", arguments={"query": "bug"}),),
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "decision": "create_github_issue",
                        "article_id": None,
                        "answer": None,
                        "summary": None,
                        "issue_title": "Application crashes",
                        "technical_context": "Crash occurs while saving.",
                    }
                )
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        asyncio.run(
            process_case(
                processing_case,
                llm,
                FailingMCPClient(
                    [SEARCH_KB, CREATE_ISSUE],
                    search_articles=[],
                ),
            )
        )

    assert processing_case.state is CaseState.PROCESSING
