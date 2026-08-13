import json
from dataclasses import dataclass
from enum import StrEnum

from l1_support_agent.agent.skills import load_skill
from l1_support_agent.application.tool_policy import (
    AgentContext,
    allowed_tool_names,
    ensure_tool_allowed,
)
from l1_support_agent.domain import Case
from l1_support_agent.llm.client import LLMClient, LLMMessage, MessageRole
from l1_support_agent.mcp.client import MCPClient

SYSTEM_PROMPT = (
    "You are an autonomous L1 support agent. Follow the operational skill below."
)

DECISION_SYSTEM_PROMPT = (
    "Choose exactly one post-KB outcome using the operational skills below. "
    "Resolve only from an adequate returned article. Otherwise use "
    "create_github_issue for an actual software defect, including reported "
    "software crashes, freezes, errors, incorrect results, failed operations, or "
    "broken UI behavior. Use escalate_l2 for every other unresolved support "
    "request."
)

POST_KB_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": [
                "resolve",
                "escalate_l2",
                "create_github_issue",
            ],
        },
        "article_id": {"type": ["string", "null"]},
        "answer": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
        "issue_title": {"type": ["string", "null"]},
        "technical_context": {"type": ["string", "null"]},
    },
    "required": [
        "decision",
        "article_id",
        "answer",
        "summary",
        "issue_title",
        "technical_context",
    ],
    "additionalProperties": False,
}

# Backward-compatible name for Scenario-A callers.
RESOLUTION_DECISION_SCHEMA = POST_KB_DECISION_SCHEMA


class AgentOutcomeKind(StrEnum):
    RESOLVED = "resolved"
    ESCALATED_L2 = "escalated_l2"
    ESCALATED_DEVELOPMENT = "escalated_development"


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    kind: AgentOutcomeKind
    message: str


@dataclass(frozen=True, slots=True)
class PostKbDecision:
    decision: str
    article_id: str | None
    answer: str | None
    summary: str | None
    issue_title: str | None
    technical_context: str | None


class AgentRuntimeError(RuntimeError):
    """The bounded agent run could not produce a valid final outcome."""


class AgentStepLimitError(AgentRuntimeError):
    """The agent exceeded its configured maximum number of steps."""


def _parse_articles(result: object) -> list[dict[str, object]]:
    if not isinstance(result, dict):
        raise AgentRuntimeError("search_kb returned invalid structured content")

    articles = result.get("articles")
    if not isinstance(articles, list):
        raise AgentRuntimeError("search_kb result must contain an articles list")

    parsed_articles: list[dict[str, object]] = []
    for article in articles:
        if not isinstance(article, dict):
            raise AgentRuntimeError("search_kb article must be an object")
        article_id = article.get("id")
        if not isinstance(article_id, str) or not article_id.strip():
            raise AgentRuntimeError(
                "search_kb article must contain a non-empty string id"
            )
        parsed_articles.append(article)

    return parsed_articles


def _decision_prompt(case: Case, articles: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "task": (
                "Choose exactly one outcome. Resolve only from an adequate returned "
                "article. Otherwise route actual software defects to "
                "create_github_issue. Reported software crashes, freezes, errors, "
                "incorrect results, failed operations, and broken UI behavior are "
                "software defects; they do not require an invented root cause. "
                "Route every other unresolved support request to escalate_l2 "
                "without inventing a diagnosis."
            ),
            "ticket": {
                "title": case.ticket.title,
                "description": case.ticket.description,
                "category": case.category,
                "priority": case.priority,
                "metadata": case.ticket.metadata,
            },
            "retrieved_articles": articles,
            "required_output": {
                "decision": (
                    "resolve, escalate_l2, or create_github_issue"
                ),
                "article_id": "selected article id, or null",
                "answer": "concise grounded user-facing answer, or null",
                "summary": "concise factual L2 problem summary, or null",
                "issue_title": "useful development issue title, or null",
                "technical_context": "technical defect context, or null",
            },
        },
        ensure_ascii=False,
    )


def _parse_decision(content: str) -> PostKbDecision:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AgentRuntimeError("LLM returned invalid post-KB JSON") from error

    if not isinstance(payload, dict):
        raise AgentRuntimeError("LLM post-KB decision must be an object")

    decision = payload.get("decision")
    article_id = payload.get("article_id")
    answer = payload.get("answer")
    summary = payload.get("summary")
    issue_title = payload.get("issue_title")
    technical_context = payload.get("technical_context")

    if decision not in {
        "resolve",
        "escalate_l2",
        "create_github_issue",
    }:
        raise AgentRuntimeError("LLM returned an invalid post-KB decision")
    if article_id is not None and not isinstance(article_id, str):
        raise AgentRuntimeError("Resolution article_id must be a string or null")
    if answer is not None and not isinstance(answer, str):
        raise AgentRuntimeError("Resolution answer must be a string or null")
    if summary is not None and not isinstance(summary, str):
        raise AgentRuntimeError("Escalation summary must be a string or null")
    if issue_title is not None and not isinstance(issue_title, str):
        raise AgentRuntimeError("Development issue title must be a string or null")
    if technical_context is not None and not isinstance(technical_context, str):
        raise AgentRuntimeError("Technical context must be a string or null")

    return PostKbDecision(
        decision=decision,
        article_id=article_id,
        answer=answer,
        summary=summary,
        issue_title=issue_title,
        technical_context=technical_context,
    )


def _validated_answer(
    decision: PostKbDecision,
    articles: list[dict[str, object]],
) -> str:
    article_id = decision.article_id
    if article_id is None or not article_id.strip():
        raise AgentRuntimeError("Resolved decision requires a non-empty article_id")

    returned_ids = {article["id"] for article in articles}
    if article_id not in returned_ids:
        raise AgentRuntimeError("Resolved decision selected an unknown article_id")

    answer = decision.answer
    if answer is None or not answer.strip():
        raise AgentRuntimeError("Resolved decision requires a non-empty answer")

    return answer


def _ticket_reference(case: Case) -> str:
    for key in ("url", "link", "ticket_url"):
        value = case.ticket.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return f"{case.ticket.source}:{case.ticket.source_id}"


def _ticket_errors_logs(case: Case) -> str:
    available: dict[str, object] = {}
    for key in ("errors", "error", "logs", "stack_trace"):
        if key in case.ticket.metadata:
            available[key] = case.ticket.metadata[key]
    if not available:
        return "Not provided"
    return json.dumps(available, ensure_ascii=False)


async def _apply_post_kb_decision(
    decision: PostKbDecision,
    articles: list[dict[str, object]],
    case: Case,
    context: AgentContext,
    discovered_tool_names: frozenset[str],
    mcp_client: MCPClient,
) -> AgentOutcome:
    if decision.decision == "resolve":
        return AgentOutcome(
            kind=AgentOutcomeKind.RESOLVED,
            message=_validated_answer(decision, articles),
        )

    if decision.decision == "escalate_l2":
        summary = decision.summary
        if summary is None or not summary.strip():
            raise AgentRuntimeError("L2 escalation requires a non-empty summary")

        tool_name = "escalate_l2"
        ensure_tool_allowed(tool_name, case, context)
        if tool_name not in discovered_tool_names:
            raise AgentRuntimeError("Required MCP tool 'escalate_l2' is unavailable")

        result = await mcp_client.call_tool(
            tool_name,
            {
                "summary": summary,
                "ticket_reference": _ticket_reference(case),
            },
        )
        if not isinstance(result, dict):
            raise AgentRuntimeError("escalate_l2 returned invalid content")
        message_id = result.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise AgentRuntimeError(
                "escalate_l2 did not return an integer message_id"
            )

        return AgentOutcome(
            kind=AgentOutcomeKind.ESCALATED_L2,
            message=summary,
        )

    issue_title = decision.issue_title
    if issue_title is None or not issue_title.strip():
        raise AgentRuntimeError(
            "Development escalation requires a non-empty issue title"
        )
    technical_context = decision.technical_context
    if technical_context is None or not technical_context.strip():
        raise AgentRuntimeError(
            "Development escalation requires non-empty technical context"
        )

    tool_name = "create_github_issue"
    ensure_tool_allowed(tool_name, case, context)
    if tool_name not in discovered_tool_names:
        raise AgentRuntimeError(
            "Required MCP tool 'create_github_issue' is unavailable"
        )

    result = await mcp_client.call_tool(
        tool_name,
        {
            "title": issue_title,
            "technical_context": technical_context,
            "ticket_description": case.ticket.description,
            "errors_logs": _ticket_errors_logs(case),
            "ticket_reference": _ticket_reference(case),
        },
    )
    if not isinstance(result, dict):
        raise AgentRuntimeError("create_github_issue returned invalid content")
    issue_url = result.get("issue_url")
    if not isinstance(issue_url, str) or not issue_url.strip():
        raise AgentRuntimeError("create_github_issue did not return an issue URL")

    return AgentOutcome(
        kind=AgentOutcomeKind.ESCALATED_DEVELOPMENT,
        message=issue_url,
    )


async def run_support_agent(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> AgentOutcome:
    """Choose and execute one bounded support outcome after KB investigation."""

    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    context = AgentContext()
    kb_skill = load_skill("kb-investigation")
    l2_skill = load_skill("l2-escalation")
    development_skill = load_skill("development-escalation")
    discovered_tools = await mcp_client.list_tools()
    discovered_tool_names = frozenset(tool.name for tool in discovered_tools)
    ticket_payload = {
        "title": case.ticket.title,
        "description": case.ticket.description,
        "category": case.category,
        "priority": case.priority,
    }
    messages = [
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"{SYSTEM_PROMPT}\n\n{kb_skill.instructions}",
        ),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(ticket_payload, ensure_ascii=False),
        ),
    ]
    retrieved_articles: list[dict[str, object]] | None = None

    for _ in range(max_steps):
        if context.kb_searched:
            if retrieved_articles is None:
                raise AgentRuntimeError("Knowledge search state is inconsistent")
            decision_messages = [
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        f"{DECISION_SYSTEM_PROMPT}\n\n"
                        f"{kb_skill.instructions}\n\n"
                        f"{l2_skill.instructions}\n\n"
                        f"{development_skill.instructions}"
                    ),
                ),
                LLMMessage(
                    role=MessageRole.USER,
                    content=_decision_prompt(case, retrieved_articles),
                ),
            ]
            response = await llm.chat(
                decision_messages,
                response_schema=POST_KB_DECISION_SCHEMA,
                tools=[],
            )
            if response.tool_calls:
                raise AgentRuntimeError(
                    "LLM requested a tool while making the post-KB decision"
                )
            return await _apply_post_kb_decision(
                _parse_decision(response.content),
                retrieved_articles,
                case,
                context,
                discovered_tool_names,
                mcp_client,
            )

        allowed_names = allowed_tool_names(case, context)
        visible_tools = [
            tool for tool in discovered_tools if tool.name in allowed_names
        ]
        response = await llm.chat(messages, tools=visible_tools)

        if not response.tool_calls:
            raise AgentRuntimeError(
                "Agent returned a final answer before searching the knowledge base"
            )
        if len(response.tool_calls) != 1:
            raise AgentRuntimeError("Agent must request exactly one tool at a time")

        tool_call = response.tool_calls[0]
        ensure_tool_allowed(tool_call.name, case, context)
        result = await mcp_client.call_tool(tool_call.name, tool_call.arguments)
        retrieved_articles = _parse_articles(result)
        context = AgentContext(kb_searched=True)

    raise AgentStepLimitError(f"Agent exceeded the {max_steps}-step limit")


async def run_resolution_agent(
    case: Case,
    llm: LLMClient,
    mcp_client: MCPClient,
    *,
    max_steps: int = 4,
) -> str:
    """Run the support agent and return its successful outcome message."""

    outcome = await run_support_agent(
        case,
        llm,
        mcp_client,
        max_steps=max_steps,
    )
    return outcome.message
