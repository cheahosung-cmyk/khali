"""텔레그램 알림 (선택). 토큰/챗ID 미설정 시 조용히 비활성화."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            httpx.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            logger.warning("텔레그램 전송 실패: %s", e)
