"""LLM Council 오케스트레이터.

ChatGPT, Claude, Gemini 를 각자의 강점에 맞춰 순서대로 호출하여
하나의 통합된 최종 답변을 만든다.

단계 구성(순서/담당 AI/모델/역할 프롬프트/입력 연결)은 council.yaml 로 자유롭게
바꿀 수 있다. 설정 파일이 없으면 기본 4단계를 사용한다:

    1. Drafter     (ChatGPT) - 초안 작성     : 범용성 작업에 강함
    2. Skeptic     (Claude)  - 비판 및 수정   : 긴 글 분석/비판에 강함
    3. Verifier    (Gemini)  - 검증 및 선별   : 정보 탐색/문맥 이해에 강함
    4. Synthesizer (ChatGPT) - 최종본 종합     : 종합 정리
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config import Settings, load_settings
from .providers import Provider, build_provider
from .stages import StageConfig, build_user_prompt, load_stages


@dataclass
class StageResult:
    """한 단계의 실행 결과."""

    name: str  # 단계 식별자
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
        """최종 답변(마지막 단계 산출물)."""
        return self.stages[-1].output if self.stages else ""

    @property
    def used_mock(self) -> bool:
        """단계 중 하나라도 mock 을 썼는지 여부."""
        return any(not s.is_live for s in self.stages)


class Council:
    """LLM Council 실행기."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        providers: Optional[dict] = None,
        stages: Optional[List[StageConfig]] = None,
        config_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            settings: 설정 객체(없으면 환경/.env 에서 로드)
            providers: 단계이름 -> Provider 매핑을 직접 주입(테스트/커스텀용).
            stages: 단계 목록을 직접 주입(주면 설정 파일 로딩을 건너뜀).
            config_path: 단계 설정 파일 경로(council.yaml 등). stages 보다 우선순위 낮음.
        """
        self.settings = settings or load_settings()
        self._override = providers or {}
        if stages is not None:
            self.stages: List[StageConfig] = stages
        else:
            self.stages = load_stages(self.settings, path=config_path)
        # 단계 이름 -> 입력 블록에 표시할 라벨
        self._label_map: Dict[str, str] = {
            s.name: s.resolved_label() for s in self.stages
        }

    def _model_for(self, stage: StageConfig) -> str:
        """단계에 사용할 모델명을 결정한다(단계 지정 > vendor 기본)."""
        if stage.model:
            return stage.model
        return {
            "openai": self.settings.openai_model,
            "anthropic": self.settings.anthropic_model,
            "gemini": self.settings.gemini_model,
        }[stage.vendor]

    def _provider_for(self, stage: StageConfig) -> Provider:
        if stage.name in self._override:
            return self._override[stage.name]
        return build_provider(
            stage.vendor, self._model_for(stage), self.settings, role=stage.name
        )

    def run(
        self,
        question: str,
        materials: str = "",
        *,
        on_stage: Optional[Callable[[StageResult], None]] = None,
    ) -> CouncilResult:
        """구성된 단계들을 순서대로 실행한다.

        Args:
            question: 사용자의 목표/질문
            materials: 참고 자료(선택)
            on_stage: 각 단계가 끝날 때마다 호출되는 콜백(진행 표시용)

        Returns:
            CouncilResult
        """
        result = CouncilResult(question=question)
        outputs: Dict[str, str] = {}

        for stage in self.stages:
            provider = self._provider_for(stage)
            user = build_user_prompt(
                stage, question, materials, outputs, self._label_map
            )
            output = provider.complete(stage.system, user)
            outputs[stage.name] = output

            stage_result = StageResult(
                name=stage.name,
                title=stage.title,
                provider=provider.label,
                is_live=provider.is_live,
                output=output,
            )
            result.stages.append(stage_result)
            if on_stage is not None:
                on_stage(stage_result)

        return result
