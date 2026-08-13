from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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

ProcessService = Callable[
    [str, RuntimeConfig],
    Awaitable[TicketProcessingResult],
]
LearnService = Callable[
    [UUID, str, RuntimeConfig],
    Awaitable[KnowledgeLearningResult],
]

_APPLICATION_ERRORS = (
    AgentRuntimeError,
    KnowledgeLearningError,
    SkillLoadError,
    ToolNotAllowedError,
    ValueError,
)


class LearnRequest(BaseModel):
    verified_resolution: str


def create_app(
    *,
    process_service: ProcessService = run_ticket_processing,
    learn_service: LearnService = run_verified_resolution_learning,
    config: RuntimeConfig | None = None,
) -> FastAPI:
    application = FastAPI(title="L1 Support Agent")

    def runtime_config() -> RuntimeConfig:
        return RuntimeConfig.from_env() if config is None else config

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/tickets/{ticket_id}/process")
    async def process_ticket(ticket_id: str) -> dict[str, object]:
        try:
            result = await process_service(ticket_id, runtime_config())
        except _APPLICATION_ERRORS as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return serialize_ticket_result(result)

    @application.post("/cases/{case_id}/learn")
    async def learn(case_id: UUID, request: LearnRequest) -> dict[str, object]:
        resolution = request.verified_resolution.strip()
        if not resolution:
            raise HTTPException(
                status_code=422,
                detail="verified_resolution must not be empty",
            )
        try:
            result = await learn_service(case_id, resolution, runtime_config())
        except _APPLICATION_ERRORS as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return serialize_learning_result(result)

    return application


app = create_app()
