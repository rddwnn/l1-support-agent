import asyncio
import json
import sqlite3
from uuid import uuid4

import pytest

from l1_support_agent.application.learn_from_resolution import (
    KNOWLEDGE_DECISION_SCHEMA,
    KnowledgeLearningError,
    KnowledgeLearningStatus,
    learn_from_verified_resolution,
    learned_article_id,
)
from l1_support_agent.domain import Case, CaseState, Ticket
from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.llm.client import (
    LLMMessage,
    LLMResponse,
    ToolDefinition,
)
from l1_support_agent.persistence.database import connect_database, init_database
from l1_support_agent.persistence.repositories import CaseRepository, TicketRepository


@pytest.fixture
def connection(tmp_path) -> sqlite3.Connection:
    database_path = tmp_path / "learning.db"
    init_database(database_path)
    connection = connect_database(database_path)
    yield connection
    connection.close()


class FakeLLMClient:
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


def decision_response(
    decision: str,
    *,
    existing_article_id: str | None = None,
    title: str | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(
            {
                "decision": decision,
                "existing_article_id": existing_article_id,
                "title": title,
            }
        )
    )


def persist_case(
    connection: sqlite3.Connection,
    state: CaseState,
    *,
    source_id: str = "42",
    category: str = "network",
) -> tuple[Case, CaseRepository, KnowledgeRepository]:
    ticket = Ticket(
        source="mockapi",
        source_id=source_id,
        user="alice",
        title="Office VPN disconnects every hour",
        description="The VPN gateway drops active sessions once per hour.",
    )
    ticket_repository = TicketRepository(connection)
    case_repository = CaseRepository(connection)
    ticket_repository.save(ticket)

    case = Case.from_ticket(ticket)
    case.state = state
    case.category = category
    case.priority = "high"
    case_repository.save(case)
    return case, case_repository, KnowledgeRepository(connection)


def article_count(connection: sqlite3.Connection) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM knowledge_articles"
    ).fetchone()[0]


def test_escalated_l2_verified_resolution_creates_searchable_article(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )
    resolution = (
        "Updated the edge-router firmware and restarted the VPN gateway service."
    )
    llm = FakeLLMClient(
        [decision_response("create", title="Hourly VPN gateway disconnects")]
    )

    result = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            resolution,
            case_repository,
            knowledge_repository,
            llm,
        )
    )

    assert result.status is KnowledgeLearningStatus.CREATED
    assert result.article_id == learned_article_id(case.id)
    article = knowledge_repository.get(result.article_id)
    assert article is not None
    assert article.category == "network"
    assert resolution in article.content
    assert case.ticket.title in article.content
    assert knowledge_repository.search("edge router firmware") == [article]
    assert case_repository.get(case.id) == case
    assert llm.calls[0][1] == KNOWLEDGE_DECISION_SCHEMA
    assert llm.calls[0][2] == []
    assert "# Knowledge Update" in llm.calls[0][0][0].content
    assert resolution in llm.calls[0][0][1].content


def test_escalated_development_case_creates_article(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_DEVELOPMENT,
        category="software",
    )
    llm = FakeLLMClient(
        [decision_response("create", title="Prevent hourly VPN session loss")]
    )

    result = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            "Deployed the verified session-renewal patch version 2.4.1.",
            case_repository,
            knowledge_repository,
            llm,
        )
    )

    article = knowledge_repository.get(result.article_id or "")
    assert result.status is KnowledgeLearningStatus.CREATED
    assert article is not None
    assert article.category == "software"
    assert case_repository.get(case.id).state is CaseState.ESCALATED_DEVELOPMENT


@pytest.mark.parametrize(
    "state",
    [
        CaseState.NEW,
        CaseState.PROCESSING,
        CaseState.AWAITING_USER,
        CaseState.RESOLVED,
    ],
)
def test_unsupported_case_state_cannot_learn(
    connection: sqlite3.Connection,
    state: CaseState,
) -> None:
    case, case_repository, knowledge_repository = persist_case(connection, state)
    llm = FakeLLMClient([])

    with pytest.raises(KnowledgeLearningError, match="not eligible"):
        asyncio.run(
            learn_from_verified_resolution(
                case.id,
                "Verified fix",
                case_repository,
                knowledge_repository,
                llm,
            )
        )

    assert article_count(connection) == 0
    assert llm.calls == []


def test_missing_case_is_rejected(connection: sqlite3.Connection) -> None:
    case_repository = CaseRepository(connection)
    knowledge_repository = KnowledgeRepository(connection)

    with pytest.raises(KnowledgeLearningError, match="does not exist"):
        asyncio.run(
            learn_from_verified_resolution(
                uuid4(),
                "Verified fix",
                case_repository,
                knowledge_repository,
                FakeLLMClient([]),
            )
        )


def test_empty_verified_resolution_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )
    llm = FakeLLMClient([])

    with pytest.raises(KnowledgeLearningError, match="must not be empty"):
        asyncio.run(
            learn_from_verified_resolution(
                case.id,
                "  ",
                case_repository,
                knowledge_repository,
                llm,
            )
        )

    assert article_count(connection) == 0
    assert llm.calls == []


def add_covering_article(repository: KnowledgeRepository) -> KnowledgeArticle:
    article = KnowledgeArticle(
        id="existing-vpn-fix",
        title="Hourly VPN disconnects",
        content=(
            "For hourly VPN gateway disconnects, update edge-router firmware and "
            "restart the gateway service."
        ),
        category="network",
    )
    repository.add(article)
    return article


def test_existing_adequate_article_is_selected_without_new_write(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )
    existing = add_covering_article(knowledge_repository)
    llm = FakeLLMClient(
        [decision_response("skip_existing", existing_article_id=existing.id)]
    )

    result = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            "Update edge-router firmware and restart the VPN gateway service.",
            case_repository,
            knowledge_repository,
            llm,
        )
    )

    assert result.status is KnowledgeLearningStatus.COVERED_BY_EXISTING
    assert result.article_id is None
    assert result.existing_article_id == existing.id
    assert article_count(connection) == 1
    assert knowledge_repository.get(learned_article_id(case.id)) is None


def test_skip_existing_rejects_article_outside_candidates(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )
    add_covering_article(knowledge_repository)
    llm = FakeLLMClient(
        [decision_response("skip_existing", existing_article_id="not-returned")]
    )

    with pytest.raises(KnowledgeLearningError, match="outside retrieved candidates"):
        asyncio.run(
            learn_from_verified_resolution(
                case.id,
                "Update edge-router firmware and restart the VPN gateway service.",
                case_repository,
                knowledge_repository,
                llm,
            )
        )

    assert article_count(connection) == 1
    assert knowledge_repository.get(learned_article_id(case.id)) is None


def test_repeated_learning_returns_same_article_without_second_llm_call(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )
    llm = FakeLLMClient(
        [decision_response("create", title="Hourly VPN disconnects")]
    )

    first = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            "Restarted the VPN gateway after updating edge-router firmware.",
            case_repository,
            knowledge_repository,
            llm,
        )
    )
    second = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            "Restarted the VPN gateway after updating edge-router firmware.",
            case_repository,
            knowledge_repository,
            llm,
        )
    )

    assert first.status is KnowledgeLearningStatus.CREATED
    assert second.status is KnowledgeLearningStatus.ALREADY_EXISTS
    assert first.article_id == second.article_id == learned_article_id(case.id)
    assert len(llm.calls) == 1
    assert article_count(connection) == 1


def test_article_content_uses_verified_input_not_llm_resolution(
    connection: sqlite3.Connection,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_DEVELOPMENT,
        category="software",
    )
    verified = "Applied verified patch 7.2 and confirmed stable sessions for 24 hours."
    llm = FakeLLMClient(
        [decision_response("create", title="Stable VPN session renewal")]
    )

    result = asyncio.run(
        learn_from_verified_resolution(
            case.id,
            verified,
            case_repository,
            knowledge_repository,
            llm,
        )
    )

    article = knowledge_repository.get(result.article_id or "")
    assert article is not None
    assert article.content == (
        "Problem\n"
        "Office VPN disconnects every hour\n"
        "The VPN gateway drops active sessions once per hour.\n\n"
        "Verified resolution\n"
        f"{verified}"
    )
    decision_payload = json.loads(llm.calls[0][0][1].content)
    assert decision_payload["verified_resolution"] == verified
    assert set(KNOWLEDGE_DECISION_SCHEMA["properties"]) == {
        "decision",
        "existing_article_id",
        "title",
    }


@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(content="not-json"),
        LLMResponse(content="[]"),
        LLMResponse(
            content=json.dumps(
                {
                    "decision": "create",
                    "existing_article_id": None,
                    "title": "Title",
                    "resolution": "Invented by LLM",
                }
            )
        ),
        decision_response("create", title="  "),
    ],
)
def test_malformed_llm_decision_is_rejected_without_write(
    connection: sqlite3.Connection,
    response: LLMResponse,
) -> None:
    case, case_repository, knowledge_repository = persist_case(
        connection,
        CaseState.ESCALATED_L2,
    )

    with pytest.raises(KnowledgeLearningError):
        asyncio.run(
            learn_from_verified_resolution(
                case.id,
                "Verified gateway restart",
                case_repository,
                knowledge_repository,
                FakeLLMClient([response]),
            )
        )

    assert article_count(connection) == 0
    assert knowledge_repository.get(learned_article_id(case.id)) is None
