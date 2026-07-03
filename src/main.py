"""Khali CLI.

사용 예:
    khali "우리 인스타 채널을 50만 팔로워로 키우려면?"
    khali "질문" --materials "참고자료..."
    khali "질문" --final-only
    khali "질문" --mock

이 세션처럼 대화 중에 질문이 주어지면, 이 명령어를 실행해 4단계 council
(초안→비판→검증→종합)을 자동으로 돌리고 최종 답변을 얻을 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .config import load_settings
from .council import Council, StageResult


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="khali",
        description=(
            "LLM Council - ChatGPT/Claude/Gemini 를 각자 강점에 맞춰 "
            "순서대로 호출해 통합된 답변을 만듭니다."
        ),
    )
    parser.add_argument("question", help="목표 또는 질문")
    parser.add_argument(
        "-m",
        "--materials",
        default="",
        help="참고 자료(선택)",
    )
    parser.add_argument(
        "--final-only",
        action="store_true",
        help="중간 단계는 숨기고 최종 답변만 출력",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="실제 API 키가 있어도 모의(mock) 응답으로 강제 실행",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="단계 구성 파일 경로(council.yaml 등). 생략 시 자동 탐색 후 기본 4단계",
    )
    return parser


def _print_stage(stage: StageResult) -> None:
    live = "🟢 LIVE" if stage.is_live else "⚪ MOCK"
    print(f"\n{'─' * 60}")
    print(f"{stage.title}  [{stage.provider}] {live}")
    print("─" * 60)
    print(stage.output)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 진입점."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.mock:
        settings.force_mock = True

    try:
        council = Council(settings=settings, config_path=args.config)
    except Exception as exc:  # 설정 파일 오류를 사용자 친화적으로 표시
        print(f"❌ 단계 구성 로드 실패: {exc}", file=sys.stderr)
        return 2

    if args.final_only:
        result = council.run(args.question, args.materials)
    else:
        print(f"질문: {args.question}")
        result = council.run(
            args.question, args.materials, on_stage=_print_stage
        )

    print(f"\n{'=' * 60}")
    print("✅ 최종 통합 답변")
    if result.used_mock:
        print("   (※ 일부/전체가 모의 응답입니다. .env 에 API 키를 넣으면 실제 모델이 동작합니다.)")
    print("=" * 60)
    print(result.final)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
