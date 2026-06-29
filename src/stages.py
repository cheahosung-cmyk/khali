"""단계(stage) 구성 - 설정으로 자유롭게 정의.

단계 순서, 담당 AI(vendor), 모델, 역할 프롬프트(system), 이전 단계 입력 연결을
council.yaml(또는 .json)에서 정의할 수 있다. 설정 파일이 없으면 기본 4단계를 쓴다.

council.yaml 예시:

    stages:
      - name: drafter
        title: "1. Drafter (ChatGPT) · 초안 작성"
        vendor: openai
        model: gpt-4o          # 생략 시 vendor 기본 모델 사용
        label: 초안             # 다음 단계에 입력으로 들어갈 때 붙는 이름
        include: []            # 입력으로 가져올 이전 단계 이름들
        system: |
          너는 Drafter 다 ...
      - name: skeptic
        vendor: anthropic
        label: 비판
        include: [drafter]
        system: |
          너는 Skeptic 이다 ...
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import prompts
from .config import Settings

VALID_VENDORS = {"openai", "anthropic", "gemini"}


@dataclass
class StageConfig:
    """한 단계의 구성 정의."""

    name: str  # 고유 식별자
    title: str  # 사람이 읽는 제목
    vendor: str  # openai | anthropic | gemini
    system: str  # 역할(시스템) 프롬프트
    model: Optional[str] = None  # 생략 시 vendor 기본 모델
    label: str = ""  # 출력이 다음 단계에 주입될 때 붙는 이름(생략 시 name)
    include: List[str] = field(default_factory=list)  # 입력으로 넣을 이전 단계들

    def resolved_label(self) -> str:
        return self.label or self.name


# ---------------------------------------------------------------------------
# 기본 4단계 (council.yaml 이 없을 때 사용)
# ---------------------------------------------------------------------------
DEFAULT_STAGES: List[StageConfig] = [
    StageConfig(
        name="drafter",
        title="1. Drafter (ChatGPT) · 초안 작성",
        vendor="openai",
        system=prompts.DRAFTER_SYSTEM,
        label="초안",
        include=[],
    ),
    StageConfig(
        name="skeptic",
        title="2. Skeptic (Claude) · 비판 및 수정",
        vendor="anthropic",
        system=prompts.SKEPTIC_SYSTEM,
        label="비판",
        include=["drafter"],
    ),
    StageConfig(
        name="verifier",
        title="3. Verifier (Gemini) · 검증 및 선별",
        vendor="gemini",
        system=prompts.VERIFIER_SYSTEM,
        label="검증",
        include=["drafter", "skeptic"],
    ),
    StageConfig(
        name="synthesizer",
        title="4. Synthesizer (ChatGPT) · 최종본 종합",
        vendor="openai",
        system=prompts.SYNTHESIZER_SYSTEM,
        label="최종",
        include=["drafter", "skeptic", "verifier"],
    ),
]


class StageConfigError(ValueError):
    """단계 구성이 잘못되었을 때 발생."""


def _coerce_stage(raw: dict, index: int) -> StageConfig:
    """딕셔너리(파일에서 읽은) 한 개를 StageConfig 로 변환."""
    if "name" not in raw:
        raise StageConfigError(f"stages[{index}]: 'name' 이 필요합니다.")
    name = str(raw["name"])
    vendor = str(raw.get("vendor", "")).lower()
    if vendor not in VALID_VENDORS:
        raise StageConfigError(
            f"stage '{name}': vendor 는 {sorted(VALID_VENDORS)} 중 하나여야 합니다 "
            f"(받은 값: {raw.get('vendor')!r})."
        )
    system = raw.get("system")
    if not system or not str(system).strip():
        raise StageConfigError(f"stage '{name}': 'system' 프롬프트가 필요합니다.")

    include = raw.get("include", []) or []
    if isinstance(include, str):
        include = [include]
    include = [str(x) for x in include]

    return StageConfig(
        name=name,
        title=str(raw.get("title", name)),
        vendor=vendor,
        system=str(system).strip(),
        model=(str(raw["model"]) if raw.get("model") else None),
        label=str(raw.get("label", "")),
        include=include,
    )


def validate_stages(stages: List[StageConfig]) -> None:
    """단계 목록의 정합성을 검사한다.

    - 이름 중복 금지
    - include 는 '앞서 정의된' 단계만 참조 가능(순환/전방참조 방지)
    """
    if not stages:
        raise StageConfigError("최소 1개 이상의 stage 가 필요합니다.")

    seen: set = set()
    for stage in stages:
        if stage.name in seen:
            raise StageConfigError(f"stage 이름이 중복됩니다: '{stage.name}'.")
        for dep in stage.include:
            if dep not in seen:
                raise StageConfigError(
                    f"stage '{stage.name}': include 의 '{dep}' 는 "
                    "앞선 단계에 존재하지 않습니다(순서를 확인하세요)."
                )
        seen.add(stage.name)


def parse_stages(data: dict) -> List[StageConfig]:
    """파싱된 dict({'stages': [...]})에서 StageConfig 목록을 만든다."""
    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list):
        raise StageConfigError("설정에 'stages' 리스트가 필요합니다.")
    stages = [_coerce_stage(raw, i) for i, raw in enumerate(raw_stages)]
    validate_stages(stages)
    return stages


def _read_config_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith((".yaml", ".yml")):
        import yaml  # 지연 import

        return yaml.safe_load(text) or {}
    if path.endswith(".json"):
        return json.loads(text) if text.strip() else {}
    # 확장자 불명 시 yaml 로 시도
    import yaml

    return yaml.safe_load(text) or {}


# 기본으로 탐색할 설정 파일 후보
_DEFAULT_CONFIG_CANDIDATES = ["council.yaml", "council.yml", "council.json"]


def resolve_config_path(settings: Settings) -> Optional[str]:
    """사용할 설정 파일 경로를 결정한다.

    우선순위: settings.council_config > 환경변수 COUNCIL_CONFIG >
    작업 디렉터리의 council.yaml/yml/json. 없으면 None(기본 단계 사용).
    """
    explicit = getattr(settings, "council_config", None) or os.environ.get(
        "COUNCIL_CONFIG"
    )
    if explicit:
        return explicit
    for candidate in _DEFAULT_CONFIG_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def load_stages(
    settings: Settings, *, path: Optional[str] = None
) -> List[StageConfig]:
    """설정에 따라 단계 목록을 로드한다.

    path 가 주어지면 그 파일을, 아니면 resolve_config_path 결과를 사용한다.
    설정 파일이 없으면 DEFAULT_STAGES 를 돌려준다.
    """
    config_path = path or resolve_config_path(settings)
    if not config_path:
        return list(DEFAULT_STAGES)
    if not os.path.exists(config_path):
        raise StageConfigError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    data = _read_config_file(config_path)
    return parse_stages(data)


def build_user_prompt(
    stage: StageConfig,
    question: str,
    materials: str,
    outputs: Dict[str, str],
    label_map: Dict[str, str],
) -> str:
    """단계의 사용자 프롬프트를 생성한다.

    원래 질문 + (자료) + include 로 지정된 이전 단계 산출물 블록으로 구성된다.
    """
    parts = [f"원래 목표/질문:\n{question}\n"]

    if materials:
        parts.append(f"자료:\n{materials}\n")
    elif not stage.include:
        # 첫 단계인데 자료가 없을 때만 표시
        parts.append("자료:\n(별도 자료 없음)\n")

    for dep in stage.include:
        block_label = label_map.get(dep, dep)
        parts.append(f"[{block_label}]\n\"\"\"\n{outputs.get(dep, '')}\n\"\"\"\n")

    return "\n".join(parts)
