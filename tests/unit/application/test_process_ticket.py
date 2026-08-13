import asyncio
import json
import sqlite3

import pytest

from l1_support_agent.application.process_ticket import process_ticket_by_id
from l1_support_agent.domain import Case, CaseState, Ticket
from l1_support_agent.llm.client import (
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)
from l1_support_agent.persistence.database import connect_database, init_database
from l1_support_agent.persistence.repositories import CaseRepository, TicketRepository

SEARCH_KB = ToolDefinition(
    name="search_kb",
    description="Search the knowledge base.",
    input_schema={"type": "object"},
)
ESCALATE_L2 = ToolDefinition(
    name="escalate_l2",
    description="Escalate to L2.",
    input_schema={"type": "object"},
)
CREATE_GITHUB_ISSUE = ToolDefinition(
    name="create_github_issue",
    description="Create a GitHub issue.",
    input_schema={"type": "object"},
)


@pytest.fixture
def connection(tmp_path) -> sqlite3.Connection:
    database_path = tmp_path / "application.db"
    init_database(database_path)
    connection = connect_database(database_path)
    yield connection
    connection.close()


@pytest.fixture
def ticket() -> Ticket:
    return Ticket(
        source="mockapi",
        source_id="42",
        user="alice",
        title="Computer beeps and does not boot",
        description="The computer emits three beeps during startup.",
        metadata={"url": "https://support.test/tickets/42"},
    )


class FakeTicketClient:
    def __init__(self, ticket: Ticket) -> None:
        self.ticket = ticket
        self.calls: list[str] = []

    async def get_ticket(self, ticket_id: str) -> Ticket:
        self.calls.append(ticket_id)
        return self.ticket


class ScriptedLLMClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[
            tuple[
                list[LLMMessage],
                dict[str, object] | None,
                list[ToolDefinition] | None,
            ]
        ] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self.calls.append((list(messages), response_schema, tools))
        return next(self._responses)


class FakeMCPClient:
    def __init__(
        self,
        tools: list[ToolDefinition],
        *,
        articles: list[dict[str, object]],
        fail_tool: str | None = None,
    ) -> None:
        self.tools = tools
        self.articles = articles
        self.fail_tool = fail_tool
        self.list_tools_calls = 0
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> list[ToolDefinition]:
        self.list_tools_calls += 1
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        self.calls.append((name, arguments))
        if name == self.fail_tool:
            raise RuntimeError(f"{name} failed")
        if name == "search_kb":
            return {"articles": self.articles}
        if name == "escalate_l2":
            return {"message_id": 101}
        if name == "create_github_issue":
            return {"issue_url": "https://github.test/acme/app/issues/202"}
        raise AssertionError(f"Unexpected tool: {name}")


def triage_response(category: str) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(
            {
                "category": category,
                "priority": "high",
                "reasoning": "Test classification",
            }
        )
    )


def search_response(query: str) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=(ToolCall(name="search_kb", arguments={"query": query}),),
    )


def decision_response(decision: str, **values: object) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(
            {
                "decision": decision,
                "article_id": None,
                "answer": None,
                "summary": None,
                "issue_title": None,
                "technical_context": None,
                **values,
            }
        )
    )


def repositories(
    connection: sqlite3.Connection,
) -> tuple[TicketRepository, CaseRepository]:
    return TicketRepository(connection), CaseRepository(connection)


def test_new_known_kb_ticket_is_triaged_resolved_and_persisted(
    connection: sqlite3.Connection,
    ticket: Ticket,
) -> None:
    ticket_repository, case_repository = repositories(connection)
    llm = ScriptedLLMClient(
        [
            triage_response("hardware"),
            search_response("three beeps"),
            decision_response(
                "resolve",
                article_id="kb-beeps",
                answer="Reseat the memory modules and retry startup.",
            ),
        ]
    )
    mcp = FakeMCPClient(
        [SEARCH_KB],
        articles=[
            {
                "id": "kb-beeps",
                "title": "POST beep codes",
                "content": "Reseat the memory modules and retry startup.",
            }
        ],
    )

    result = asyncio.run(
        process_ticket_by_id(
            "42",
            FakeTicketClient(ticket),
            ticket_repository,
            case_repository,
            llm,
            mcp,
        )
    )

    persisted = case_repository.get(result.case_id)
    assert result.source_ticket_id == "42"
    assert result.final_state is CaseState.RESOLVED
    assert result.category == "hardware"
    assert result.priority == "high"
    assert result.outcome_message == "Reseat the memory modules and retry startup."
    assert persisted is not None
    assert persisted.state is CaseState.RESOLVED
    assert len(llm.calls) == 3


@pytest.mark.parametrize(
    (
        "category",
        "decision",
        "tools",
        "decision_values",
        "expected_state",
        "expected_tool",
    ),
    [
        (
            "network",
            "escalate_l2",
            [SEARCH_KB, ESCALATE_L2],
            {"summary": "Office network is unavailable."},
            CaseState.ESCALATED_L2,
            "escalate_l2",
        ),
        (
            "software",
            "create_github_issue",
            [SEARCH_KB, CREATE_GITHUB_ISSUE],
            {
                "issue_title": "Login returns HTTP 500",
                "technical_context": "Valid credentials trigger a database timeout.",
            },
            CaseState.ESCALATED_DEVELOPMENT,
            "create_github_issue",
        ),
    ],
)
def test_new_ticket_escalation_is_persisted(
    connection: sqlite3.Connection,
    ticket: Ticket,
    category: str,
    decision: str,
    tools: list[ToolDefinition],
    decision_values: dict[str, object],
    expected_state: CaseState,
    expected_tool: str,
) -> None:
    ticket_repository, case_repository = repositories(connection)
    llm = ScriptedLLMClient(
        [
            triage_response(category),
            search_response(ticket.title),
            decision_response(decision, **decision_values),
        ]
    )
    mcp = FakeMCPClient(tools, articles=[])

    result = asyncio.run(
        process_ticket_by_id(
            "42",
            FakeTicketClient(ticket),
            ticket_repository,
            case_repository,
            llm,
            mcp,
        )
    )

    persisted = case_repository.get(result.case_id)
    assert result.final_state is expected_state
    assert persisted is not None
    assert persisted.state is expected_state
    assert [name for name, _ in mcp.calls] == ["search_kb", expected_tool]


@pytest.mark.parametrize(
    "terminal_state",
    [
        CaseState.RESOLVED,
        CaseState.ESCALATED_L2,
        CaseState.ESCALATED_DEVELOPMENT,
    ],
)
def test_existing_terminal_case_returns_without_agent_side_effects(
    connection: sqlite3.Connection,
    ticket: Ticket,
    terminal_state: CaseState,
) -> None:
    ticket_repository, case_repository = repositories(connection)
    ticket_repository.save(ticket)
    case = Case.from_ticket(ticket)
    case.state = terminal_state
    case.category = "hardware"
    case.priority = "high"
    case_repository.save(case)
    ticket_client = FakeTicketClient(ticket)
    llm = ScriptedLLMClient([])
    mcp = FakeMCPClient([], articles=[])

    result = asyncio.run(
        process_ticket_by_id(
            "42",
            ticket_client,
            ticket_repository,
            case_repository,
            llm,
            mcp,
        )
    )

    assert result.case_id == case.id
    assert result.final_state is terminal_state
    assert result.outcome_message is None
    assert llm.calls == []
    assert mcp.list_tools_calls == 0
    assert mcp.calls == []
    ticket_count = connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    case_count = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    assert (ticket_count, case_count) == (1, 1)


def test_existing_processing_case_continues_without_retriage(
    connection: sqlite3.Connection,
    ticket: Ticket,
) -> None:
    ticket_repository, case_repository = repositories(connection)
    ticket_repository.save(ticket)
    case = Case.from_ticket(ticket)
    case.state = CaseState.PROCESSING
    case.category = "hardware"
    case.priority = "high"
    case_repository.save(case)
    llm = ScriptedLLMClient(
        [
            search_response("three beeps"),
            decision_response(
                "resolve",
                article_id="kb-beeps",
                answer="Reseat the memory modules.",
            ),
        ]
    )
    mcp = FakeMCPClient(
        [SEARCH_KB],
        articles=[
            {
                "id": "kb-beeps",
                "title": "Beep codes",
                "content": "Reseat the memory modules.",
            }
        ],
    )

    result = asyncio.run(
        process_ticket_by_id(
            "42",
            FakeTicketClient(ticket),
            ticket_repository,
            case_repository,
            llm,
            mcp,
        )
    )

    assert result.case_id == case.id
    assert result.final_state is CaseState.RESOLVED
    assert len(llm.calls) == 2
    assert llm.calls[0][1] is None
    assert [tool.name for tool in llm.calls[0][2] or []] == ["search_kb"]


def test_failed_support_action_does_not_persist_terminal_state(
    connection: sqlite3.Connection,
    ticket: Ticket,
) -> None:
    ticket_repository, case_repository = repositories(connection)
    llm = ScriptedLLMClient(
        [
            triage_response("network"),
            search_response("office network unavailable"),
            decision_response(
                "escalate_l2",
                summary="Office network is unavailable.",
            ),
        ]
    )
    mcp = FakeMCPClient(
        [SEARCH_KB, ESCALATE_L2],
        articles=[],
        fail_tool="escalate_l2",
    )

    with pytest.raises(RuntimeError, match="escalate_l2 failed"):
        asyncio.run(
            process_ticket_by_id(
                "42",
                FakeTicketClient(ticket),
                ticket_repository,
                case_repository,
                llm,
                mcp,
            )
        )

    persisted = case_repository.get(Case.from_ticket(ticket).id)
    assert persisted is not None
    assert persisted.state is CaseState.PROCESSING
    assert persisted.category == "network"
    assert persisted.priority == "high"
