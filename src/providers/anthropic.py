"""Anthropic (Claude) provider.

`anthropic` SDK 를 지연 import 한다. 미설치 시 안내 메시지를 띄운다.
실제 호출은 API 키가 있을 때만 일어난다(없으면 build_provider 가 mock 으로 대체).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Provider


@dataclass
class AnthropicProvider(Provider):
    """Anthropic Messages API 기반 provider."""

    vendor: str = "anthropic"
    is_live: bool = True
    api_key: str = field(default="")
    max_tokens: int = 4096

    def complete(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - 선택적 의존성
            raise RuntimeError(
                "anthropic 패키지가 필요합니다. `pip install anthropic` 후 다시 시도하세요."
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "".join(parts).strip()
