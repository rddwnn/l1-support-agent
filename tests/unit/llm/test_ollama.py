import asyncio
import json

import httpx
import pytest

from l1_support_agent.llm.client import (
    LLMMessage,
    MessageRole,
)
from l1_support_agent.llm.ollama import OllamaClient


def test_chat_sends_expected_request_and_returns_content() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "hello",
                }
            },
        )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = OllamaClient(
                http_client,
                base_url="http://ollama.test/",
                model="test-model",
            )

            return await client.chat(
                [
                    LLMMessage(
                        role=MessageRole.USER,
                        content="Hello",
                    )
                ]
            )

    response = asyncio.run(exercise())

    assert response.content == "hello"

    assert len(requests) == 1
    request = requests[0]

    assert request.method == "POST"
    assert str(request.url) == "http://ollama.test/api/chat"

    payload = json.loads(request.content)

    assert payload == {
        "model": "test-model",
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ],
        "stream": False,
        "think": False,
    }


def test_chat_sends_response_schema_as_ollama_format() -> None:
    received_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received_payload.update(json.loads(request.content))

        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"priority":"high"}',
                }
            },
        )

    schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "priority": {
                "type": "string",
            }
        },
        "required": ["priority"],
    }

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = OllamaClient(
                http_client,
                base_url="http://ollama.test",
                model="test-model",
            )

            await client.chat(
                [
                    LLMMessage(
                        role=MessageRole.USER,
                        content="Classify",
                    )
                ],
                response_schema=schema,
            )

    asyncio.run(exercise())

    assert received_payload["format"] == schema    


@pytest.mark.parametrize(
    ("response_payload", "error_message"),
    [
        ({}, "must contain a message object"),
        ({"message": None}, "must contain a message object"),
        (
            {"message": {}},
            "must contain string content",
        ),
        (
            {"message": {"content": None}},
            "must contain string content",
        ),
    ],
)
def test_chat_rejects_invalid_response_shapes(
    response_payload: object,
    error_message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = OllamaClient(
                http_client,
                base_url="http://ollama.test",
                model="test-model",
            )

            await client.chat([])

    with pytest.raises(TypeError, match=error_message):
        asyncio.run(exercise())


def test_chat_propagates_http_status_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": "model unavailable"},
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = OllamaClient(
                http_client,
                base_url="http://ollama.test",
                model="test-model",
            )

            await client.chat([])

    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(exercise())

    assert error.value.response.status_code == 503


def test_chat_serializes_multiple_messages() -> None:
    received_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received_payload.update(json.loads(request.content))

        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "response",
                }
            },
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = OllamaClient(
                http_client,
                base_url="http://ollama.test",
                model="test-model",
            )

            await client.chat(
                [
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content="You are a support agent.",
                    ),
                    LLMMessage(
                        role=MessageRole.USER,
                        content="My application crashed.",
                    ),
                ]
            )

    asyncio.run(exercise())

    assert received_payload["messages"] == [
        {
            "role": "system",
            "content": "You are a support agent.",
        },
        {
            "role": "user",
            "content": "My application crashed.",
        },
    ]
    