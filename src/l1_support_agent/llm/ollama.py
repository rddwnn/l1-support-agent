import httpx

from .client import LLMMessage, LLMResponse


class OllamaClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def chat(
            self, 
            messages: list[LLMMessage],
            *,
            response_schema: dict[str, object] | None = None,
    ) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in messages
            ],
            "stream": False,
            "think": False
        }
        if response_schema is not None:
            payload["format"] = response_schema

        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        message = data.get("message")
        if not isinstance(message, dict):
            raise TypeError("Ollama response must contain a message object")

        content = message.get("content")
        if not isinstance(content, str):
            raise TypeError("Ollama message must contain string content")

        return LLMResponse(content=content)
    