"""설정 관리.

API 키와 각 단계(stage)에 사용할 모델을 환경변수/.env 에서 읽어온다.
키가 없으면 자동으로 mock 모드로 동작한다.
"""

from __future__ import annotations

from typing import Optional

try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    _HAS_PYDANTIC_SETTINGS = True
except ImportError:  # pragma: no cover - pydantic-settings 미설치 환경 대비
    _HAS_PYDANTIC_SETTINGS = False


if _HAS_PYDANTIC_SETTINGS:

    class Settings(BaseSettings):
        """환경변수 기반 설정.

        .env 파일 또는 실제 환경변수에서 값을 읽는다.
        """

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # --- API 키 (없으면 해당 provider 는 mock 으로 대체) ---
        openai_api_key: Optional[str] = Field(default=None)
        anthropic_api_key: Optional[str] = Field(default=None)
        gemini_api_key: Optional[str] = Field(default=None)

        # --- vendor 별 기본 모델 (단계에서 model 을 지정하지 않으면 사용) ---
        openai_model: str = Field(default="gpt-4o")
        anthropic_model: str = Field(default="claude-opus-4-8")
        gemini_model: str = Field(default="gemini-1.5-pro")

        # --- 단계 구성 파일 경로 (없으면 council.yaml 자동 탐색 → 기본 4단계) ---
        council_config: Optional[str] = Field(default=None)

        # --- mock 모드 강제 (실제 키가 있어도 mock 으로 동작) ---
        force_mock: bool = Field(default=False)

else:  # pragma: no cover - 폴백: 순수 os.environ 기반

    import os
    from dataclasses import dataclass

    @dataclass
    class Settings:  # type: ignore[no-redef]
        openai_api_key: Optional[str] = None
        anthropic_api_key: Optional[str] = None
        gemini_api_key: Optional[str] = None
        openai_model: str = "gpt-4o"
        anthropic_model: str = "claude-opus-4-8"
        gemini_model: str = "gemini-1.5-pro"
        council_config: Optional[str] = None
        force_mock: bool = False

        def __post_init__(self) -> None:
            self.openai_api_key = self.openai_api_key or os.environ.get("OPENAI_API_KEY")
            self.anthropic_api_key = self.anthropic_api_key or os.environ.get(
                "ANTHROPIC_API_KEY"
            )
            self.gemini_api_key = self.gemini_api_key or os.environ.get("GEMINI_API_KEY")
            self.council_config = self.council_config or os.environ.get(
                "COUNCIL_CONFIG"
            )
            self.force_mock = self.force_mock or os.environ.get(
                "FORCE_MOCK", ""
            ).lower() in ("1", "true", "yes")


def load_settings() -> "Settings":
    """설정을 로드한다."""
    return Settings()
