"""LLM provider 들.

각 provider 는 동일한 인터페이스(`Provider.complete`)를 따른다.
API 키가 없으면 자동으로 MockProvider 로 대체된다.
"""

from __future__ import annotations

from typing import Optional

from ..config import Settings
from .anthropic import AnthropicProvider
from .base import Provider
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai import OpenAIProvider

__all__ = [
    "Provider",
    "MockProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "build_provider",
]


def build_provider(
    vendor: str,
    model: str,
    settings: Settings,
    *,
    role: Optional[str] = None,
) -> Provider:
    """vendor 이름과 설정으로 provider 를 생성한다.

    키가 없거나 force_mock 이 켜져 있으면 MockProvider 를 돌려준다.

    Args:
        vendor: "openai" | "anthropic" | "gemini"
        model: 모델명
        settings: 설정 객체
        role: 단계 역할 이름(mock 응답에 표시용)
    """
    vendor = vendor.lower()

    if settings.force_mock:
        return MockProvider(model=model, vendor=vendor, role=role)

    if vendor == "openai":
        if settings.openai_api_key:
            return OpenAIProvider(model=model, api_key=settings.openai_api_key)
        return MockProvider(model=model, vendor=vendor, role=role)

    if vendor == "anthropic":
        if settings.anthropic_api_key:
            return AnthropicProvider(model=model, api_key=settings.anthropic_api_key)
        return MockProvider(model=model, vendor=vendor, role=role)

    if vendor == "gemini":
        if settings.gemini_api_key:
            return GeminiProvider(model=model, api_key=settings.gemini_api_key)
        return MockProvider(model=model, vendor=vendor, role=role)

    raise ValueError(f"알 수 없는 vendor: {vendor!r}")
