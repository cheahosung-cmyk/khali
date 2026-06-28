"""LLM Council 오케스트레이터.

ChatGPT, Claude, Gemini 를 각자의 강점에 맞춰 순서대로 호출하여
하나의 통합된 최종 답변을 만든다.

    1. Drafter     (ChatGPT) - 초안 작성     : 범용성 작업에 강함
    2. Skeptic     (Claude)  - 비판 및 수정   : 긴 글 분석/비판에 강함
    3. Verifier    (Gemini)  - 검증 및 선별   : 정보 탐색/문맥 이해에 강함
    4. Synthesizer (ChatGPT) - 최종본 종합     : 종합 정리
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import prompts
from .config import Settings, load_settings
from .providers import Provider, build_provider


@dataclass
class StageResult:
    """한 단계의 실행 결과."""

    name: str  # "drafter" | "skeptic" | "verifier" | "synthesizer"
    title: str  # 사람이 읽기 좋은 제목
    provider: str  # 라벨 (예: "openai:gpt-4o" / "mock:gpt-4o")
    is_live: bool  # 실제 API 호출 여부
    output: str  # 단계 산출물


@dataclass
class CouncilResult:
    """council 전체 실행 결과."""

    question: str
    stages: List[StageResult] = field(default_factory=list)

    @property
    def final(self) -> str:
        """최종 종합 답변(마지막 단계 산출물)."""
        return self.stages[-1].output if self.stages else ""

    @property
    def used_mock(self) -> bool:
        """단계 중 하나라도 mock 을 썼는지 여부."""
        return any(not s.is_live for s in self.stages)


# 단계 정의: (역할이름, 사람이 읽을 제목, vendor, 설정에서 모델 가져오는 함수)
_STAGE_DEFS = [
    ("drafter", "1. Drafter (ChatGPT) · 초안 작성", "openai", lambda s: s.drafter_model),
    ("skeptic", "2. Skeptic (Claude) · 비판 및 수정", "anthropic", lambda s: s.skeptic_model),
    ("verifier", "3. Verifier (Gemini) · 검증 및 선별", "gemini", lambda s: s.verifier_model),
    (
        "synthesizer",
        "4. Synthesizer (ChatGPT) · 최종본 종합",
        "openai",
        lambda s: s.synthesizer_model,
    ),
]


class Council:
    """LLM Council 실행기."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        providers: Optional[dict] = None,
    ) -> None:
        """
        Args:
            settings: 설정 객체(없으면 환경/.env 에서 로드)
            providers: 역할이름 -> Provider 매핑을 직접 주입(테스트/커스텀용).
                       지정한 역할만 덮어쓰고, 나머지는 설정으로 자동 생성.
        """
        self.settings = settings or load_settings()
        self._override = providers or {}

    def _provider_for(self, role: str, vendor: str, model: str) -> Provider:
        if role in self._override:
            return self._override[role]
        return build_provider(vendor, model, self.settings, role=role)

    def run(
        self,
        question: str,
        materials: str = "",
        *,
        on_stage: Optional[Callable[[StageResult], None]] = None,
    ) -> CouncilResult:
        """council 4단계를 순서대로 실행한다.

        Args:
            question: 사용자의 목표/질문
            materials: 참고 자료(선택)
            on_stage: 각 단계가 끝날 때마다 호출되는 콜백(진행 표시용)

        Returns:
            CouncilResult
        """
        result = CouncilResult(question=question)
        draft = critique = verification = ""

        for role, title, vendor, model_getter in _STAGE_DEFS:
            provider = self._provider_for(role, vendor, model_getter(self.settings))

            if role == "drafter":
                system = prompts.DRAFTER_SYSTEM
                user = prompts.drafter_user(question, materials)
            elif role == "skeptic":
                system = prompts.SKEPTIC_SYSTEM
                user = prompts.skeptic_user(question, draft)
            elif role == "verifier":
                system = prompts.VERIFIER_SYSTEM
                user = prompts.verifier_user(question, draft, critique)
            else:  # synthesizer
                system = prompts.SYNTHESIZER_SYSTEM
                user = prompts.synthesizer_user(question, draft, critique, verification)

            output = provider.complete(system, user)

            if role == "drafter":
                draft = output
            elif role == "skeptic":
                critique = output
            elif role == "verifier":
                verification = output

            stage = StageResult(
                name=role,
                title=title,
                provider=provider.label,
                is_live=provider.is_live,
                output=output,
            )
            result.stages.append(stage)
            if on_stage is not None:
                on_stage(stage)

        return result
