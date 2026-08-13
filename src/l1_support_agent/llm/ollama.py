import httpx

from .client import (
    LLMMessage,
    LLMResponse,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


class OllamaClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, object] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [_serialize_message(message) for message in messages],
            "stream": False,
            "think": False,
        }
        if response_schema is not None:
            payload["format"] = response_schema
        if tools is not None:
            payload["tools"] = [_serialize_tool(tool) for tool in tools]

        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Ollama response must be an object")

        message = data.get("message")
        if not isinstance(message, dict):
            raise TypeError("Ollama response must contain a message object")

        tool_calls = _parse_tool_calls(message.get("tool_calls", []))
        content = message.get("content")
        if content is None and tool_calls:
            content = ""
        if not isinstance(content, str):
            raise TypeError("Ollama message must contain string content")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
        )


def _serialize_message(message: LLMMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
        "content": message.content,
    }

    if message.role is MessageRole.TOOL:
        if message.tool_name is None:
            raise ValueError("Tool messages must identify a tool name")
        payload["tool_name"] = message.tool_name

    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]

    return payload


def _serialize_tool(tool: ToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _parse_tool_calls(payload: object) -> tuple[ToolCall, ...]:
    if not isinstance(payload, list):
        raise TypeError("Ollama tool_calls must be a list")

    tool_calls = []
    for item in payload:
        if not isinstance(item, dict):
            raise TypeError("Ollama tool call must be an object")

        function = item.get("function")
        if not isinstance(function, dict):
            raise TypeError("Ollama tool call must contain a function object")

        name = function.get("name")
        if not isinstance(name, str):
            raise TypeError("Ollama tool call name must be a string")
        if not name:
            raise ValueError("Ollama tool call name must not be empty")

        arguments = function.get("arguments")
        if not isinstance(arguments, dict):
            raise TypeError("Ollama tool call arguments must be an object")

        tool_calls.append(
            ToolCall(
                name=name,
                arguments=arguments,
            )
        )

    return tuple(tool_calls)
