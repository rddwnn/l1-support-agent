import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from l1_support_agent.agent.skills import load_skill
from l1_support_agent.domain import Case, CaseState
from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.llm.client import LLMClient, LLMMessage, MessageRole
from l1_support_agent.persistence.repositories import CaseRepository

KNOWLEDGE_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["create", "skip_existing"],
        },
        "existing_article_id": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
    },
    "required": ["decision", "existing_article_id", "title"],
    "additionalProperties": False,
}

_LEARNABLE_STATES = frozenset(
    {
        CaseState.ESCALATED_L2,
        CaseState.ESCALATED_DEVELOPMENT,
    }
)


class KnowledgeLearningStatus(StrEnum):
    CREATED = "created"
    ALREADY_EXISTS = "already_exists"
    COVERED_BY_EXISTING = "covered_by_existing"


@dataclass(frozen=True, slots=True)
class KnowledgeLearningResult:
    case_id: UUID
    status: KnowledgeLearningStatus
    article_id: str | None = None
    existing_article_id: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeDecision:
    decision: str
    existing_article_id: str | None
    title: str | None


class KnowledgeLearningError(RuntimeError):
    """Verified resolution knowledge cannot be captured safely."""


def learned_article_id(case_id: UUID) -> str:
    return f"learned-case-{case_id}"


def _decision_prompt(
    case: Case,
    verified_resolution: str,
    candidates: list[KnowledgeArticle],
) -> str:
    return json.dumps(
        {
            "task": (
                "Decide whether existing KB coverage is adequate. Do not generate "
                "or modify the verified resolution."
            ),
            "case": {
                "title": case.ticket.title,
                "description": case.ticket.description,
                "category": case.category,
            },
            "verified_resolution": verified_resolution,
            "candidate_articles": [
                {
                    "id": article.id,
                    "title": article.title,
                    "content": article.content,
                    "category": article.category,
                }
                for article in candidates
            ],
            "required_output": {
                "decision": "create or skip_existing",
                "existing_article_id": "adequate candidate id, or null",
                "title": "concise new article title, or null",
            },
        },
        ensure_ascii=False,
    )


def _parse_decision(content: str) -> KnowledgeDecision:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise KnowledgeLearningError("LLM returned invalid knowledge decision JSON") from error

    if not isinstance(payload, dict):
        raise KnowledgeLearningError("Knowledge decision must be an object")
    if set(payload) != {"decision", "existing_article_id", "title"}:
        raise KnowledgeLearningError("Knowledge decision has invalid fields")

    decision = payload["decision"]
    existing_article_id = payload["existing_article_id"]
    title = payload["title"]
    if decision not in {"create", "skip_existing"}:
        raise KnowledgeLearningError("Knowledge decision is invalid")
    if existing_article_id is not None and not isinstance(existing_article_id, str):
        raise KnowledgeLearningError(
            "Knowledge decision existing_article_id must be a string or null"
        )
    if title is not None and not isinstance(title, str):
        raise KnowledgeLearningError("Knowledge decision title must be a string or null")

    return KnowledgeDecision(
        decision=decision,
        existing_article_id=existing_article_id,
        title=title,
    )


def _article_content(case: Case, verified_resolution: str) -> str:
    return (
        "Problem\n"
        f"{case.ticket.title}\n"
        f"{case.ticket.description}\n\n"
        "Verified resolution\n"
        f"{verified_resolution}"
    )


async def learn_from_verified_resolution(
    case_id: UUID,
    verified_resolution: str,
    case_repository: CaseRepository,
    knowledge_repository: KnowledgeRepository,
    llm: LLMClient,
) -> KnowledgeLearningResult:
    """Capture trusted post-escalation knowledge through an explicit workflow."""

    case = case_repository.get(case_id)
    if case is None:
        raise KnowledgeLearningError(f"Case {case_id} does not exist")
    if case.state not in _LEARNABLE_STATES:
        raise KnowledgeLearningError(
            f"Case state {case.state.value!r} is not eligible for knowledge learning"
        )

    resolution = verified_resolution.strip()
    if not resolution:
        raise KnowledgeLearningError("Verified resolution must not be empty")

    article_id = learned_article_id(case.id)
    existing_learned_article = knowledge_repository.get(article_id)
    if existing_learned_article is not None:
        return KnowledgeLearningResult(
            case_id=case.id,
            status=KnowledgeLearningStatus.ALREADY_EXISTS,
            article_id=existing_learned_article.id,
        )

    candidates = knowledge_repository.search(
        f"{case.ticket.title} {case.ticket.description} {resolution}"
    )
    skill = load_skill("knowledge-update")
    response = await llm.chat(
        [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "Evaluate verified post-escalation knowledge using the "
                    "operational skill below.\n\n"
                    f"{skill.instructions}"
                ),
            ),
            LLMMessage(
                role=MessageRole.USER,
                content=_decision_prompt(case, resolution, candidates),
            ),
        ],
        response_schema=KNOWLEDGE_DECISION_SCHEMA,
        tools=[],
    )
    if response.tool_calls:
        raise KnowledgeLearningError("Knowledge decision must not request tools")

    decision = _parse_decision(response.content)
    if decision.decision == "skip_existing":
        selected_id = decision.existing_article_id
        if selected_id is None or not selected_id.strip():
            raise KnowledgeLearningError(
                "skip_existing requires a non-empty existing_article_id"
            )
        candidate_ids = {article.id for article in candidates}
        if selected_id not in candidate_ids:
            raise KnowledgeLearningError(
                "skip_existing selected an article outside retrieved candidates"
            )
        return KnowledgeLearningResult(
            case_id=case.id,
            status=KnowledgeLearningStatus.COVERED_BY_EXISTING,
            existing_article_id=selected_id,
        )

    title = decision.title
    if title is None or not title.strip():
        raise KnowledgeLearningError("create requires a non-empty title")

    article = KnowledgeArticle(
        id=article_id,
        title=title.strip(),
        content=_article_content(case, resolution),
        category=case.category,
    )
    knowledge_repository.add(article)
    return KnowledgeLearningResult(
        case_id=case.id,
        status=KnowledgeLearningStatus.CREATED,
        article_id=article.id,
    )
