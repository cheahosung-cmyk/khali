"""Council 흐름 테스트 (mock 모드)."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.council import Council, StageResult
from src.providers import build_provider
from src.providers.mock import MockProvider
from src.stages import (
    DEFAULT_STAGES,
    StageConfig,
    StageConfigError,
    load_stages,
    parse_stages,
    validate_stages,
)


def _mock_settings() -> Settings:
    s = Settings()
    s.force_mock = True
    return s


# --- provider 선택 ----------------------------------------------------------


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


# --- 기본 4단계 흐름 --------------------------------------------------------


def test_council_runs_default_four_stages_in_order():
    """council 은 기본 4단계를 정해진 순서로 실행한다."""
    council = Council(settings=_mock_settings())
    result = council.run("우리 채널을 50만 팔로워로 키우려면?")

    names = [s.name for s in result.stages]
    assert names == ["drafter", "skeptic", "verifier", "synthesizer"]
    assert result.used_mock is True
    assert result.final  # 최종 답변이 비어있지 않음


def test_on_stage_callback_called_per_stage():
    """각 단계마다 콜백이 호출된다."""
    seen = []

    def cb(stage: StageResult) -> None:
        seen.append(stage.name)

    council = Council(settings=_mock_settings())
    council.run("질문", on_stage=cb)
    assert seen == ["drafter", "skeptic", "verifier", "synthesizer"]


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
    assert "내질문" in captured["skeptic_user"]
    assert "초안" in captured["skeptic_user"]  # drafter 의 label 블록


def test_provider_override_is_used():
    """providers 인자로 특정 단계를 직접 주입할 수 있다."""

    class FixedProvider(MockProvider):
        def complete(self, system: str, user: str) -> str:
            return "고정된-초안-출력"

    fixed = FixedProvider(model="custom", role="drafter")
    council = Council(settings=_mock_settings(), providers={"drafter": fixed})
    result = council.run("질문")
    assert result.stages[0].output == "고정된-초안-출력"


# --- 단계 구성 변경(핵심 기능) ---------------------------------------------


def test_custom_stages_injected_directly():
    """stages 인자로 임의 구성을 주입해 실행할 수 있다."""
    stages = [
        StageConfig(
            name="solo",
            title="단일 단계",
            vendor="anthropic",
            system="너는 답을 작성한다.",
        )
    ]
    council = Council(settings=_mock_settings(), stages=stages)
    result = council.run("질문")
    assert [s.name for s in result.stages] == ["solo"]
    # mock 모드: 라벨엔 의도한 vendor 가 남고, is_live=False 로 구분된다
    assert result.stages[0].provider.startswith("anthropic:")
    assert result.stages[0].is_live is False


def test_reordered_and_reduced_stages():
    """단계 수를 줄이고 순서를 바꿔도 동작한다."""
    stages = [
        StageConfig(name="draft", title="초안", vendor="openai", system="작성"),
        StageConfig(
            name="final",
            title="종합",
            vendor="anthropic",
            system="종합",
            include=["draft"],
        ),
    ]
    council = Council(settings=_mock_settings(), stages=stages)
    result = council.run("질문")
    assert [s.name for s in result.stages] == ["draft", "final"]


def test_parse_stages_from_dict():
    """dict 구성(파일에서 읽은 형태)을 파싱한다."""
    data = {
        "stages": [
            {"name": "a", "vendor": "openai", "system": "s1"},
            {"name": "b", "vendor": "gemini", "system": "s2", "include": ["a"]},
        ]
    }
    stages = parse_stages(data)
    assert [s.name for s in stages] == ["a", "b"]
    assert stages[1].include == ["a"]


def test_per_stage_model_override_in_label():
    """단계에 model 을 지정하면 provider 라벨에 반영된다."""
    stages = [
        StageConfig(
            name="x", title="x", vendor="openai", system="s", model="gpt-4o-mini"
        )
    ]
    council = Council(settings=_mock_settings(), stages=stages)
    result = council.run("질문")
    assert result.stages[0].provider == "openai:gpt-4o-mini"


def test_vendor_default_model_when_unset():
    """단계에 model 이 없으면 vendor 기본 모델을 쓴다."""
    s = _mock_settings()
    s.anthropic_model = "claude-test-model"
    stages = [StageConfig(name="x", title="x", vendor="anthropic", system="s")]
    council = Council(settings=s, stages=stages)
    result = council.run("질문")
    assert result.stages[0].provider == "anthropic:claude-test-model"


# --- 검증(validation) -------------------------------------------------------


def test_invalid_vendor_raises():
    with pytest.raises(StageConfigError):
        parse_stages({"stages": [{"name": "a", "vendor": "bogus", "system": "s"}]})


def test_missing_system_raises():
    with pytest.raises(StageConfigError):
        parse_stages({"stages": [{"name": "a", "vendor": "openai"}]})


def test_forward_reference_in_include_raises():
    """include 가 아직 정의되지 않은 단계를 참조하면 오류."""
    with pytest.raises(StageConfigError):
        validate_stages(
            [
                StageConfig(
                    name="a",
                    title="a",
                    vendor="openai",
                    system="s",
                    include=["b"],  # b 는 뒤에 나옴
                ),
                StageConfig(name="b", title="b", vendor="openai", system="s"),
            ]
        )


def test_duplicate_stage_name_raises():
    with pytest.raises(StageConfigError):
        validate_stages(
            [
                StageConfig(name="a", title="a", vendor="openai", system="s"),
                StageConfig(name="a", title="a2", vendor="openai", system="s"),
            ]
        )


# --- 설정 파일 로딩 ---------------------------------------------------------


def test_load_stages_defaults_when_no_file(tmp_path, monkeypatch):
    """설정 파일이 없으면 기본 단계를 쓴다."""
    monkeypatch.chdir(tmp_path)  # council.yaml 이 없는 디렉터리
    monkeypatch.delenv("COUNCIL_CONFIG", raising=False)
    stages = load_stages(Settings())
    assert [s.name for s in stages] == [s.name for s in DEFAULT_STAGES]


def test_load_stages_from_yaml_file(tmp_path):
    """yaml 파일에서 단계를 로드한다."""
    cfg = tmp_path / "council.yaml"
    cfg.write_text(
        "stages:\n"
        "  - name: only\n"
        "    vendor: gemini\n"
        "    system: |\n"
        "      너는 검증자다.\n",
        encoding="utf-8",
    )
    stages = load_stages(Settings(), path=str(cfg))
    assert [s.name for s in stages] == ["only"]
    assert stages[0].vendor == "gemini"
