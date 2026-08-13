import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

import httpx

from l1_support_agent.agent.runtime import AgentRuntimeError
from l1_support_agent.agent.skills import SkillLoadError
from l1_support_agent.application.learn_from_resolution import (
    KnowledgeLearningError,
    KnowledgeLearningResult,
)
from l1_support_agent.application.process_ticket import TicketProcessingResult
from l1_support_agent.application.tool_policy import ToolNotAllowedError
from l1_support_agent.interfaces import (
    RuntimeConfig,
    run_ticket_processing,
    run_verified_resolution_learning,
    serialize_learning_result,
    serialize_ticket_result,
)
from l1_support_agent.mcp.client import MCPToolCallError

ProcessService = Callable[
    [str, RuntimeConfig],
    Awaitable[TicketProcessingResult],
]
LearnService = Callable[
    [UUID, str, RuntimeConfig],
    Awaitable[KnowledgeLearningResult],
]

_EXPECTED_ERRORS = (
    AgentRuntimeError,
    KnowledgeLearningError,
    SkillLoadError,
    ToolNotAllowedError,
    MCPToolCallError,
    httpx.HTTPError,
    ValueError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l1-support-agent")
    commands = parser.add_subparsers(dest="command", required=True)

    process_parser = commands.add_parser("process", help="Process a MockAPI ticket")
    process_parser.add_argument("ticket_id")

    learn_parser = commands.add_parser(
        "learn",
        help="Capture a human-verified post-escalation resolution",
    )
    learn_parser.add_argument("case_id")
    learn_parser.add_argument("--resolution", required=True)
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    process_service: ProcessService = run_ticket_processing,
    learn_service: LearnService = run_verified_resolution_learning,
    config: RuntimeConfig | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    runtime_config = RuntimeConfig.from_env() if config is None else config

    try:
        if args.command == "process":
            result = asyncio.run(process_service(args.ticket_id, runtime_config))
            payload = serialize_ticket_result(result)
        else:
            case_id = UUID(args.case_id)
            resolution = args.resolution.strip()
            if not resolution:
                raise ValueError("verified resolution must not be empty")
            result = asyncio.run(
                learn_service(case_id, resolution, runtime_config)
            )
            payload = serialize_learning_result(result)
    except _EXPECTED_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> None:
    raise SystemExit(run_cli())
