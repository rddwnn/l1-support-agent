import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
from mcp import StdioServerParameters

from l1_support_agent.application.learn_from_resolution import (
    KnowledgeLearningResult,
    learn_from_verified_resolution,
)
from l1_support_agent.application.process_ticket import (
    TicketProcessingResult,
    process_ticket_by_id,
)
from l1_support_agent.integrations.tickets.mcp import MCPTicketClient
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.llm.ollama import OllamaClient
from l1_support_agent.mcp.client import connect_stdio_mcp
from l1_support_agent.persistence.database import connect_database, init_database
from l1_support_agent.persistence.repositories import CaseRepository, TicketRepository


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    database_path: Path = Path("support.db")
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:4b"

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "RuntimeConfig":
        values = os.environ if environment is None else environment
        return cls(
            database_path=Path(values.get("SUPPORT_DB_PATH", "support.db")),
            llm_base_url=values.get(
                "LLM_BASE_URL",
                "http://localhost:11434",
            ).rstrip("/"),
            llm_model=values.get("LLM_MODEL", "qwen3.5:4b"),
        )

    def mcp_environment(
        self,
        environment: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        values = os.environ if environment is None else environment
        result = dict(values)
        result["SUPPORT_DB_PATH"] = str(self.database_path)
        return result


def build_mcp_server_parameters(
    config: RuntimeConfig,
    *,
    environment: Mapping[str, str] | None = None,
) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "l1_support_agent.mcp.server"],
        env=config.mcp_environment(environment),
    )


async def run_ticket_processing(
    ticket_id: str,
    config: RuntimeConfig,
) -> TicketProcessingResult:
    """Compose real resources and delegate ticket processing to the application."""

    init_database(config.database_path)
    connection = connect_database(config.database_path)
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            llm = OllamaClient(
                http_client,
                base_url=config.llm_base_url,
                model=config.llm_model,
            )
            server = build_mcp_server_parameters(config)
            async with connect_stdio_mcp(server) as mcp_client:
                ticket_client = MCPTicketClient(mcp_client)
                return await process_ticket_by_id(
                    ticket_id,
                    ticket_client,
                    TicketRepository(connection),
                    CaseRepository(connection),
                    llm,
                    mcp_client,
                )
    finally:
        connection.close()


async def run_verified_resolution_learning(
    case_id: UUID,
    verified_resolution: str,
    config: RuntimeConfig,
) -> KnowledgeLearningResult:
    """Compose real resources and delegate explicit verified learning."""

    init_database(config.database_path)
    connection = connect_database(config.database_path)
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            llm = OllamaClient(
                http_client,
                base_url=config.llm_base_url,
                model=config.llm_model,
            )
            return await learn_from_verified_resolution(
                case_id,
                verified_resolution,
                CaseRepository(connection),
                KnowledgeRepository(connection),
                llm,
            )
    finally:
        connection.close()


def serialize_ticket_result(result: TicketProcessingResult) -> dict[str, object]:
    return {
        "case_id": str(result.case_id),
        "source_ticket_id": result.source_ticket_id,
        "final_state": result.final_state.value,
        "category": result.category,
        "priority": result.priority,
        "outcome_message": result.outcome_message,
    }


def serialize_learning_result(result: KnowledgeLearningResult) -> dict[str, object]:
    return {
        "case_id": str(result.case_id),
        "status": result.status.value,
        "article_id": result.article_id,
        "existing_article_id": result.existing_article_id,
    }
