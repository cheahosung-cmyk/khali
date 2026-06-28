"""Council 흐름 테스트 (mock 모드)."""

from __future__ import annotations

from src.config import Settings
from src.council import Council, StageResult
from src.providers import build_provider
from src.providers.mock import MockProvider


def _mock_settings() -> Settings:
    s = Settings()
    s.force_mock = True
    return s


def test_build_provider_falls_back_to_mock_without_key():
    """키가 없으면 mock provider 로 대체된다."""
    s = Settings()
    s.openai_api_key = None
    s.force_mock = False
    provider = build_provider("openai", "gpt-4o", s, role="drafter")
    assert isinstance(provider, MockProvider)
    assert provider.is_live is False


def test_force_mock_overrides_keys():
    """force_mock 이면 키가 있어도 mock 을 쓴다."""
    s = Settings()
    s.openai_api_key = "sk-fake"
    s.force_mock = True
    provider = build_provider("openai", "gpt-4o", s, role="drafter")
    assert isinstance(provider, MockProvider)


def test_council_runs_four_stages_in_order():
    """council 은 4단계를 정해진 순서로 실행한다."""
    council = Council(settings=_mock_settings())
    result = council.run("우리 채널을 50만 팔로워로 키우려면?")

    names = [s.name for s in result.stages]
    assert names == ["drafter", "skeptic", "verifier", "synthesizer"]
    assert result.used_mock is True
    assert result.final  # 최종 답변이 비어있지 않음
    assert "최종본" in result.final  # synthesizer mock 산출물


def test_on_stage_callback_called_per_stage():
    """각 단계마다 콜백이 호출된다."""
    seen = []

    def cb(stage: StageResult) -> None:
        seen.append(stage.name)

    council = Council(settings=_mock_settings())
    council.run("질문", on_stage=cb)
    assert seen == ["drafter", "skeptic", "verifier", "synthesizer"]


def test_provider_override_is_used():
    """providers 인자로 특정 단계를 직접 주입할 수 있다."""

    class FixedProvider(MockProvider):
        def complete(self, system: str, user: str) -> str:
            return "고정된-초안-출력"

    fixed = FixedProvider(model="custom", role="drafter")
    council = Council(settings=_mock_settings(), providers={"drafter": fixed})
    result = council.run("질문")
    assert result.stages[0].output == "고정된-초안-출력"
    # 이후 단계는 초안을 입력으로 받는다
    assert result.stages[0].name == "drafter"


def test_stage_passes_output_forward():
    """앞 단계 산출물이 다음 단계 입력으로 전달된다."""

    captured = {}

    class CapturingSkeptic(MockProvider):
        def complete(self, system: str, user: str) -> str:
            captured["skeptic_user"] = user
            return "비판-출력"

    council = Council(
        settings=_mock_settings(),
        providers={"skeptic": CapturingSkeptic(model="c", role="skeptic")},
    )
    council.run("내질문")
    # skeptic 입력에 drafter 의 초안과 원 질문이 포함돼야 한다
    assert "내질문" in captured["skeptic_user"]
    assert "초안" in captured["skeptic_user"]
