import asyncio
import json

import pytest

from l1_support_agent.agent.triage import (
    TRIAGE_SCHEMA,
    TriageResult,
    triage_ticket,
)
from l1_support_agent.domain import Ticket
from l1_support_agent.llm.client import (
    LLMMessage,
    LLMResponse,
    ToolDefinition,
)


class FakeLLMClient:
    def __init__(self, response_content: str) -> None:
        self._response_content = response_content
        self.messages: list[LLMMessage] | None = None
        self.response_schema: dict[str, object] | None = None

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self.messages = messages
        self.response_schema = response_schema

        return LLMResponse(
            content=self._response_content,
        )


def make_ticket() -> Ticket:
    return Ticket(
        source="mockapi",
        source_id="42",
        user="alice",
        title="CRM returns 500",
        description="Saving a customer causes HTTP 500 for the whole sales team.",
        metadata={
            "category": "Ошибки в работе ПО",
            "priority": "Критический",
        },
    )


def test_triage_returns_structured_result() -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "category": "software",
                "priority": "high",
                "reasoning": "The issue blocks customer data saving.",
            }
        )
    )

    result = asyncio.run(
        triage_ticket(
            make_ticket(),
            llm,
        )
    )

    assert result == TriageResult(
        category="software",
        priority="high",
        reasoning="The issue blocks customer data saving.",
    )


def test_triage_passes_schema_to_llm() -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "category": "software",
                "priority": "high",
                "reasoning": "Reason",
            }
        )
    )

    asyncio.run(
        triage_ticket(
            make_ticket(),
            llm,
        )
    )

    assert llm.response_schema == TRIAGE_SCHEMA


def test_triage_prompt_contains_operational_skill() -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "category": "software",
                "priority": "high",
                "reasoning": "Reason",
            }
        )
    )

    asyncio.run(triage_ticket(make_ticket(), llm))

    assert llm.messages is not None
    system_prompt = llm.messages[0].content
    assert "# Triage" in system_prompt
    assert "only on ticket data" in system_prompt
    assert "Do not invent" in system_prompt
    assert "`access`" in system_prompt
    assert "`critical`" in system_prompt


def test_triage_includes_ticket_and_source_signals() -> None:
    ticket = make_ticket()

    llm = FakeLLMClient(
        json.dumps(
            {
                "category": "software",
                "priority": "high",
                "reasoning": "Reason",
            }
        )
    )

    asyncio.run(
        triage_ticket(
            ticket,
            llm,
        )
    )

    assert llm.messages is not None
    assert len(llm.messages) == 2

    user_message = llm.messages[1]
    payload = json.loads(user_message.content)

    assert payload == {
        "title": ticket.title,
        "description": ticket.description,
        "source_category": "Ошибки в работе ПО",
        "source_priority": "Критический",
    }


@pytest.mark.parametrize(
    "category",
    [
        "database",
        "security",
        "",
    ],
)
def test_triage_rejects_unknown_category(category: str) -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "category": category,
                "priority": "high",
                "reasoning": "Reason",
            }
        )
    )

    with pytest.raises(ValueError, match="Invalid triage category"):
        asyncio.run(
            triage_ticket(
                make_ticket(),
                llm,
            )
        )


@pytest.mark.parametrize(
    "priority",
    [
        "urgent",
        "very_high",
        "",
    ],
)
def test_triage_rejects_unknown_priority(priority: str) -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "category": "software",
                "priority": priority,
                "reasoning": "Reason",
            }
        )
    )

    with pytest.raises(ValueError, match="Invalid triage priority"):
        asyncio.run(
            triage_ticket(
                make_ticket(),
                llm,
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "error_message"),
    [
        (
            "category",
            123,
            "Triage category must be a string",
        ),
        (
            "priority",
            123,
            "Triage priority must be a string",
        ),
        (
            "reasoning",
            None,
            "Triage reasoning must be a string",
        ),
    ],
)
def test_triage_rejects_invalid_field_types(
    field: str,
    value: object,
    error_message: str,
) -> None:
    payload: dict[str, object] = {
        "category": "software",
        "priority": "high",
        "reasoning": "Reason",
    }

    payload[field] = value

    llm = FakeLLMClient(
        json.dumps(payload)
    )

    with pytest.raises(TypeError, match=error_message):
        asyncio.run(
            triage_ticket(
                make_ticket(),
                llm,
            )
        )


def test_triage_rejects_non_object_response() -> None:
    llm = FakeLLMClient(
        json.dumps(
            [
                "software",
                "high",
            ]
        )
    )

    with pytest.raises(
        TypeError,
        match="Triage response must be a JSON object",
    ):
        asyncio.run(
            triage_ticket(
                make_ticket(),
                llm,
            )
        )
