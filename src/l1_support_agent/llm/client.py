from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str


class LLMClient(Protocol):
    async def chat(
            self,
            messages: list[LLMMessage],
            *,
            response_schema: dict[str, object] | None = None
    ) -> LLMResponse:
        ...
