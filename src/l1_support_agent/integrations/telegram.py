import os
from dataclasses import dataclass

import httpx


class TelegramError(RuntimeError):
    """Telegram rejected an escalation message or returned invalid data."""


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured"
            )
        return cls(bot_token=bot_token, chat_id=chat_id)


class TelegramClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: TelegramConfig,
        *,
        api_url: str = "https://api.telegram.org",
    ) -> None:
        self._client = client
        self._config = config
        self._api_url = api_url.rstrip("/")

    async def send_l2_escalation(
        self,
        summary: str,
        ticket_reference: str,
    ) -> int:
        response = await self._client.post(
            f"{self._api_url}/bot{self._config.bot_token}/sendMessage",
            json={
                "chat_id": self._config.chat_id,
                "text": f"L2 escalation\n\n{summary}\n\nTicket: {ticket_reference}",
            },
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramError("Telegram API rejected the escalation message")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise TelegramError("Telegram response must contain a result object")
        message_id = result.get("message_id")
        if not isinstance(message_id, int):
            raise TelegramError("Telegram response must contain an integer message_id")

        return message_id
