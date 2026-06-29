"""OpenAI (ChatGPT) provider.

`openai` SDK 를 지연 import 한다. 미설치 시 안내 메시지를 띄운다.
실제 호출은 API 키가 있을 때만 일어난다(없으면 build_provider 가 mock 으로 대체).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Provider


@dataclass
class OpenAIProvider(Provider):
    """OpenAI Chat Completions 기반 provider."""

    vendor: str = "openai"
    is_live: bool = True
    api_key: str = field(default="")

    def complete(self, system: str, user: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 선택적 의존성
            raise RuntimeError(
                "openai 패키지가 필요합니다. `pip install openai` 후 다시 시도하세요."
            ) from exc

        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
