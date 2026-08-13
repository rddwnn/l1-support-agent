import json
from pathlib import Path
from uuid import UUID

from l1_support_agent.application.learn_from_resolution import (
    KnowledgeLearningError,
    KnowledgeLearningResult,
    KnowledgeLearningStatus,
)
from l1_support_agent.application.process_ticket import TicketProcessingResult
from l1_support_agent.cli import run_cli
from l1_support_agent.domain import CaseState
from l1_support_agent.interfaces import RuntimeConfig

CASE_ID = UUID("d5ae43d6-a10d-41aa-8c4f-a09ba86286f5")
CONFIG = RuntimeConfig(database_path=Path("test.db"))


def test_process_command_prints_json(capsys: object) -> None:
    calls: list[tuple[str, RuntimeConfig]] = []

    async def process(ticket_id: str, config: RuntimeConfig) -> TicketProcessingResult:
        calls.append((ticket_id, config))
        return TicketProcessingResult(
            case_id=CASE_ID,
            source_ticket_id=ticket_id,
            final_state=CaseState.RESOLVED,
            category="software",
            priority="medium",
            outcome_message="Restart the application.",
        )

    assert run_cli(["process", "42"], process_service=process, config=CONFIG) == 0

    output = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(output.out) == {
        "case_id": str(CASE_ID),
        "source_ticket_id": "42",
        "final_state": "resolved",
        "category": "software",
        "priority": "medium",
        "outcome_message": "Restart the application.",
    }
    assert calls == [("42", CONFIG)]


def test_learn_command_parses_uuid_and_resolution(capsys: object) -> None:
    calls: list[tuple[UUID, str, RuntimeConfig]] = []

    async def learn(
        case_id: UUID,
        resolution: str,
        config: RuntimeConfig,
    ) -> KnowledgeLearningResult:
        calls.append((case_id, resolution, config))
        return KnowledgeLearningResult(
            case_id=case_id,
            status=KnowledgeLearningStatus.CREATED,
            article_id="learned-article",
        )

    exit_code = run_cli(
        ["learn", str(CASE_ID), "--resolution", "  Verified fix  "],
        learn_service=learn,
        config=CONFIG,
    )

    assert exit_code == 0
    output = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(output.out) == {
        "case_id": str(CASE_ID),
        "status": "created",
        "article_id": "learned-article",
        "existing_article_id": None,
    }
    assert calls == [(CASE_ID, "Verified fix", CONFIG)]


def test_learn_command_rejects_invalid_uuid_without_traceback(capsys: object) -> None:
    assert run_cli(
        ["learn", "not-a-uuid", "--resolution", "Verified fix"],
        config=CONFIG,
    ) == 1

    output = capsys.readouterr()  # type: ignore[attr-defined]
    assert "error:" in output.err
    assert "Traceback" not in output.err


def test_application_error_returns_nonzero_without_traceback(capsys: object) -> None:
    async def learn(
        case_id: UUID,
        resolution: str,
        config: RuntimeConfig,
    ) -> KnowledgeLearningResult:
        raise KnowledgeLearningError("case is not eligible")

    exit_code = run_cli(
        ["learn", str(CASE_ID), "--resolution", "Verified fix"],
        learn_service=learn,
        config=CONFIG,
    )

    assert exit_code == 1
    output = capsys.readouterr()  # type: ignore[attr-defined]
    assert "case is not eligible" in output.err
    assert "Traceback" not in output.err
