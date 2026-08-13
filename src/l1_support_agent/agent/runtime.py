import json
from dataclasses import dataclass

from l1_support_agent.application.tool_policy import (
    AgentContext,
    allowed_tool_names,
    ensure_tool_allowed,
)
from l1_support_agent.domain import Case
from l1_support_agent.llm.client import LLMClient, LLMMessage, MessageRole
from l1_support_agent.mcp.client import MCPClient

SYSTEM_PROMPT = (
    "You are an autonomous L1 support agent. "
    "Use available tools to investigate the ticket. "
    "Rely on tool results rather than inventing instructions. "
    "Do not claim an action was performed unless a tool result establishes it."
)

DECISION_SYSTEM_PROMPT = (
    "You judge whether retrieved support articles solve a ticket. "
    "This is a semantic relevance decision, not a guarantee of success. "
    "When an article directly addresses the reported problem and gives applicable "
    "steps, you must select it and answer only from that article. "
    "When no article does, return no_solution."
)

RESOLUTION_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["resolve", "no_solution"],
        },
        "article_id": {"type": ["string", "null"]},
        "answer": {"type": ["string", "null"]},
    },
    "required": ["decision", "article_id", "answer"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    decision: str
    article_id: str | None
    answer: str | None


class AgentRuntimeError(RuntimeError):
    """The bounded agent run could not produce a valid final answer."""


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
                "Decide whether one retrieved article adequately solves the ticket. "
                "An article is adequate when its title or content directly matches "
                "the reported symptoms and it provides relevant actionable "
                "instructions. In that situation, decision must be resolve. Do not "
                "require proof that the instructions will certainly fix the problem. "
                "Use only information in the retrieved articles. If no article meets "
                "these criteria, return no_solution."
            ),
            "ticket": {
                "title": case.ticket.title,
                "description": case.ticket.description,
                "category": case.category,
                "priority": case.priority,
            },
            "retrieved_articles": articles,
            "required_output": {
                "decision": "resolve or no_solution",
                "article_id": "selected article id, or null",
                "answer": "concise grounded user-facing answer, or null",
            },
        },
        ensure_ascii=False,
    )


def _parse_decision(content: str) -> ResolutionDecision:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AgentRuntimeError("LLM returned invalid resolution JSON") from error

    if not isinstance(payload, dict):
        raise AgentRuntimeError("LLM resolution decision must be an object")

    decision = payload.get("decision")
    article_id = payload.get("article_id")
    answer = payload.get("answer")

    if decision not in {"resolve", "no_solution"}:
        raise AgentRuntimeError("LLM returned an invalid resolution decision")
    if article_id is not None and not isinstance(article_id, str):
        raise AgentRuntimeError("Resolution article_id must be a string or null")
    if answer is not None and not isinstance(answer, str):
        raise AgentRuntimeError("Resolution answer must be a string or null")

    return ResolutionDecision(
        decision=decision,
        article_id=article_id,
        answer=answer,
    )


def _validated_answer(
    decision: ResolutionDecision,
    articles: list[dict[str, object]],
) -> str:
    if decision.decision == "no_solution":
        raise AgentRuntimeError("Knowledge base contains no adequate solution")

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
    ticket_payload = {
        "title": case.ticket.title,
        "description": case.ticket.description,
        "category": case.category,
        "priority": case.priority,
    }
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
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
                    content=DECISION_SYSTEM_PROMPT,
                ),
                LLMMessage(
                    role=MessageRole.USER,
                    content=_decision_prompt(case, retrieved_articles),
                ),
            ]
            response = await llm.chat(
                decision_messages,
                response_schema=RESOLUTION_DECISION_SCHEMA,
                tools=[],
            )
            if response.tool_calls:
                raise AgentRuntimeError(
                    "LLM requested a tool while making the resolution decision"
                )
            return _validated_answer(
                _parse_decision(response.content),
                retrieved_articles,
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
        messages.append(
            LLMMessage(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            )
        )
        result = await mcp_client.call_tool(tool_call.name, tool_call.arguments)
        retrieved_articles = _parse_articles(result)
        context = AgentContext(kb_searched=True)
        messages.append(
            LLMMessage(
                role=MessageRole.TOOL,
                content=json.dumps(result, ensure_ascii=False),
                tool_name=tool_call.name,
            )
        )

    raise AgentStepLimitError(f"Agent exceeded the {max_steps}-step limit")
