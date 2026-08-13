import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from l1_support_agent import interfaces
from l1_support_agent.application.process_ticket import TicketProcessingResult
from l1_support_agent.domain import CaseState
from l1_support_agent.integrations.tickets.mcp import MCPTicketClient
from l1_support_agent.interfaces import (
    RuntimeConfig,
    build_mcp_server_parameters,
)
from l1_support_agent.llm.client import ToolDefinition


def test_runtime_config_uses_local_defaults() -> None:
    config = RuntimeConfig.from_env({})

    assert config.database_path == Path("support.db")
    assert config.llm_base_url == "http://localhost:11434"
    assert config.llm_model == "qwen3.5:4b"


def test_runtime_config_reads_environment_overrides() -> None:
    config = RuntimeConfig.from_env(
        {
            "SUPPORT_DB_PATH": "/tmp/test-support.db",
            "LLM_BASE_URL": "http://ollama.test:11434/",
            "LLM_MODEL": "test-model",
        }
    )

    assert config.database_path == Path("/tmp/test-support.db")
    assert config.llm_base_url == "http://ollama.test:11434"
    assert config.llm_model == "test-model"


def test_mcp_parameters_use_current_interpreter_and_shared_database() -> None:
    config = RuntimeConfig(database_path=Path("/tmp/mcp-support.db"))

    parameters = build_mcp_server_parameters(
        config,
        environment={"TELEGRAM_CHAT_ID": "test-chat"},
    )

    assert parameters.command == sys.executable
    assert parameters.args == ["-m", "l1_support_agent.mcp.server"]
    assert parameters.env is not None
    assert parameters.env["SUPPORT_DB_PATH"] == "/tmp/mcp-support.db"
    assert parameters.env["TELEGRAM_CHAT_ID"] == "test-chat"


def test_ticket_processing_composition_uses_mcp_ticket_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeMCPClient:
        async def list_tools(self) -> list[ToolDefinition]:
            return []

        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> object:
            raise AssertionError("No MCP tool should run in this composition test")

    fake_mcp = FakeMCPClient()
    captured_ticket_client: MCPTicketClient | None = None

    @asynccontextmanager
    async def fake_connection(server):
        yield fake_mcp

    async def fake_process(
        ticket_id,
        ticket_client,
        ticket_repository,
        case_repository,
        llm,
        mcp_client,
    ) -> TicketProcessingResult:
        nonlocal captured_ticket_client
        captured_ticket_client = ticket_client
        assert ticket_id == "21"
        assert mcp_client is fake_mcp
        return TicketProcessingResult(
            case_id=UUID("6cf140a6-1173-474d-a12c-c2c40f39f49a"),
            source_ticket_id="21",
            final_state=CaseState.RESOLVED,
            category="software",
            priority="high",
            outcome_message="Resolved",
        )

    monkeypatch.setattr(interfaces, "connect_stdio_mcp", fake_connection)
    monkeypatch.setattr(interfaces, "process_ticket_by_id", fake_process)

    config = RuntimeConfig(database_path=tmp_path / "composition.db")
    result = asyncio.run(interfaces.run_ticket_processing("21", config))

    assert result.final_state is CaseState.RESOLVED
    assert isinstance(captured_ticket_client, MCPTicketClient)
