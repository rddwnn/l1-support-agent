from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from l1_support_agent.api import create_app
from l1_support_agent.application.learn_from_resolution import (
    KnowledgeLearningError,
    KnowledgeLearningResult,
    KnowledgeLearningStatus,
)
from l1_support_agent.application.process_ticket import TicketProcessingResult
from l1_support_agent.domain import CaseState
from l1_support_agent.interfaces import RuntimeConfig

CASE_ID = UUID("d5ae43d6-a10d-41aa-8c4f-a09ba86286f5")
CONFIG = RuntimeConfig(database_path=Path("test.db"))


def test_health_does_not_invoke_services() -> None:
    async def unexpected_process(
        ticket_id: str,
        config: RuntimeConfig,
    ) -> TicketProcessingResult:
        raise AssertionError("process service must not run")

    async def unexpected_learn(
        case_id: UUID,
        resolution: str,
        config: RuntimeConfig,
    ) -> KnowledgeLearningResult:
        raise AssertionError("learn service must not run")

    client = TestClient(
        create_app(
            process_service=unexpected_process,
            learn_service=unexpected_learn,
            config=CONFIG,
        )
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_endpoint_serializes_application_result() -> None:
    calls: list[tuple[str, RuntimeConfig]] = []

    async def process(ticket_id: str, config: RuntimeConfig) -> TicketProcessingResult:
        calls.append((ticket_id, config))
        return TicketProcessingResult(
            case_id=CASE_ID,
            source_ticket_id=ticket_id,
            final_state=CaseState.ESCALATED_L2,
            category="infrastructure",
            priority="high",
            outcome_message="Escalated to L2.",
        )

    client = TestClient(create_app(process_service=process, config=CONFIG))

    response = client.post("/tickets/17/process")

    assert response.status_code == 200
    assert response.json() == {
        "case_id": str(CASE_ID),
        "source_ticket_id": "17",
        "final_state": "escalated_l2",
        "category": "infrastructure",
        "priority": "high",
        "outcome_message": "Escalated to L2.",
    }
    assert calls == [("17", CONFIG)]


def test_learn_endpoint_serializes_application_result() -> None:
    calls: list[tuple[UUID, str, RuntimeConfig]] = []

    async def learn(
        case_id: UUID,
        resolution: str,
        config: RuntimeConfig,
    ) -> KnowledgeLearningResult:
        calls.append((case_id, resolution, config))
        return KnowledgeLearningResult(
            case_id=case_id,
            status=KnowledgeLearningStatus.COVERED_BY_EXISTING,
            existing_article_id="kb-42",
        )

    client = TestClient(create_app(learn_service=learn, config=CONFIG))

    response = client.post(
        f"/cases/{CASE_ID}/learn",
        json={"verified_resolution": "  Verified fix  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "case_id": str(CASE_ID),
        "status": "covered_by_existing",
        "article_id": None,
        "existing_article_id": "kb-42",
    }
    assert calls == [(CASE_ID, "Verified fix", CONFIG)]


def test_learn_endpoint_rejects_invalid_uuid_and_empty_resolution() -> None:
    client = TestClient(create_app(config=CONFIG))

    invalid_uuid = client.post(
        "/cases/not-a-uuid/learn",
        json={"verified_resolution": "Verified fix"},
    )
    empty_resolution = client.post(
        f"/cases/{CASE_ID}/learn",
        json={"verified_resolution": "   "},
    )

    assert invalid_uuid.status_code == 422
    assert empty_resolution.status_code == 422


def test_expected_application_error_maps_to_client_error() -> None:
    async def learn(
        case_id: UUID,
        resolution: str,
        config: RuntimeConfig,
    ) -> KnowledgeLearningResult:
        raise KnowledgeLearningError("case is not eligible")

    client = TestClient(create_app(learn_service=learn, config=CONFIG))

    response = client.post(
        f"/cases/{CASE_ID}/learn",
        json={"verified_resolution": "Verified fix"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "case is not eligible"}
