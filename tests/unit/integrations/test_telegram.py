import asyncio
import json

import httpx
import pytest

from l1_support_agent.integrations.telegram import (
    MockTelegramClient,
    TelegramClient,
    TelegramConfig,
    TelegramError,
)


def test_mock_telegram_returns_stable_positive_message_id() -> None:
    client = MockTelegramClient()

    first = asyncio.run(
        client.send_l2_escalation("Office network unavailable", "mockapi:2")
    )
    second = asyncio.run(
        client.send_l2_escalation("Office network unavailable", "mockapi:2")
    )

    assert first == second
    assert first > 0


def test_send_l2_escalation_posts_summary_and_ticket_reference() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 321}},
        )

    async def exercise() -> int:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            return await TelegramClient(
                http_client,
                TelegramConfig(bot_token="secret-token", chat_id="-10042"),
                api_url="https://telegram.test",
            ).send_l2_escalation(
                "Office network is unavailable.",
                "https://support.test/tickets/42",
            )

    message_id = asyncio.run(exercise())

    assert message_id == 321
    assert [(request.method, str(request.url)) for request in requests] == [
        ("POST", "https://telegram.test/botsecret-token/sendMessage")
    ]
    assert json.loads(requests[0].content) == {
        "chat_id": "-10042",
        "text": (
            "L2 escalation\n\nOffice network is unavailable.\n\n"
            "Ticket: https://support.test/tickets/42"
        ),
    }


def test_send_l2_escalation_propagates_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False})

    async def exercise() -> int:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            return await TelegramClient(
                http_client,
                TelegramConfig(bot_token="token", chat_id="chat"),
            ).send_l2_escalation("Network down", "mockapi:42")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(exercise())


def test_telegram_config_requires_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(TelegramError, match="must be configured"):
        TelegramConfig.from_env()
