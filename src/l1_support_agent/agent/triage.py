import json
from dataclasses import dataclass

from l1_support_agent.agent.skills import load_skill
from l1_support_agent.domain import Ticket
from l1_support_agent.llm.client import (
    LLMClient,
    LLMMessage,
    MessageRole,
)

TRIAGE_CATEGORIES = (
    "access",
    "consultation",
    "hardware",
    "software",
    "network",
)

TRIAGE_PRIORITIES = (
    "low",
    "medium",
    "high",
    "critical",
)


TRIAGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": list(TRIAGE_CATEGORIES),
        },
        "priority": {
            "type": "string",
            "enum": list(TRIAGE_PRIORITIES),
        },
        "reasoning": {
            "type": "string",
        },
    },
    "required": [
        "category",
        "priority",
        "reasoning",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class TriageResult:
    category: str
    priority: str
    reasoning: str


async def triage_ticket(
    ticket: Ticket,
    llm: LLMClient,
) -> TriageResult:
    triage_skill = load_skill("triage")
    ticket_data = json.dumps(
        {
            "title": ticket.title,
            "description": ticket.description,
            "source_category": ticket.metadata.get("category"),
            "source_priority": ticket.metadata.get("priority"),
        },
        ensure_ascii=False,
    )

    response = await llm.chat(
        [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "You are an L1 technical support triage agent.\n\n"
                    f"{triage_skill.instructions}"
                ),
            ),
            LLMMessage(
                role=MessageRole.USER,
                content=ticket_data,
            ),
        ],
        response_schema=TRIAGE_SCHEMA,
    )

    data = json.loads(response.content)

    if not isinstance(data, dict):
        raise TypeError("Triage response must be a JSON object")

    category = data.get("category")
    priority = data.get("priority")
    reasoning = data.get("reasoning")

    if not isinstance(category, str):
        raise TypeError("Triage category must be a string")

    if category not in TRIAGE_CATEGORIES:
        raise ValueError(f"Invalid triage category: {category}")

    if not isinstance(priority, str):
        raise TypeError("Triage priority must be a string")

    if priority not in TRIAGE_PRIORITIES:
        raise ValueError(f"Invalid triage priority: {priority}")

    if not isinstance(reasoning, str):
        raise TypeError("Triage reasoning must be a string")

    return TriageResult(
        category=category,
        priority=priority,
        reasoning=reasoning,
    )
