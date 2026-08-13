import asyncio
import json

from l1_support_agent.application.triage_case import triage_case
from l1_support_agent.domain import (
    Case,
    CaseState,
    Ticket,
)
from l1_support_agent.llm.client import (
    LLMMessage,
    LLMResponse,
)


class FakeLLMClient:
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(
                {
                    "category": "hardware",
                    "priority": "high",
                    "reasoning": "The computer fails to boot.",
                }
            )
        )


def test_triage_case_starts_processing_and_applies_result() -> None:
    ticket = Ticket(
        source="mockapi",
        source_id="1",
        user="alice",
        title="Computer does not boot",
        description="The computer beeps and does not boot.",
    )

    case = Case.from_ticket(ticket)

    assert case.state == CaseState.NEW
    assert case.category is None
    assert case.priority is None

    result = asyncio.run(
        triage_case(
            case,
            FakeLLMClient(),
        )
    )

    assert case.state == CaseState.PROCESSING
    assert case.category == "hardware"
    assert case.priority == "high"

    assert result.category == "hardware"
    assert result.priority == "high"