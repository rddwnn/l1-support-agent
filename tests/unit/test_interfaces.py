import sys
from pathlib import Path

from l1_support_agent.interfaces import (
    RuntimeConfig,
    build_mcp_server_parameters,
)


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
