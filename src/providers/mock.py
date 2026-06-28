"""Mock provider - API 키 없이 전체 흐름을 테스트하기 위한 모의 응답.

실제 모델을 호출하지 않고, 입력 프롬프트를 요약한 결정적(deterministic)
응답을 만들어낸다. 단계별 역할에 맞는 그럴듯한 출력을 흉내 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Provider


def _first_lines(text: str, n: int = 3) -> str:
    """텍스트에서 비어있지 않은 앞쪽 n줄을 추려 한 줄로 합친다."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " / ".join(lines[:n]) if lines else "(입력 없음)"


@dataclass
class MockProvider(Provider):
    """결정적 모의 응답을 만드는 provider."""

    vendor: str = "mock"
    is_live: bool = False
    role: str = field(default="")

    def complete(self, system: str, user: str) -> str:
        role = self.role or "unknown"
        summary = _first_lines(user)
        header = f"[MOCK · {self.vendor}:{self.model} · role={role}]"

        if role == "drafter":
            body = (
                "초안(모의): 입력 목표를 바탕으로 핵심 결론과 3가지 실행안을 구성했습니다.\n"
                "- 핵심 결론: (모의) 주어진 목표는 단계적 접근으로 달성 가능합니다.\n"
                "- [확인 필요] 구체적 수치/출처는 검증 단계에서 확인이 필요합니다."
            )
        elif role == "skeptic":
            body = (
                "비판(모의): 칭찬 없이 문제점만 정리합니다.\n"
                "- 과장: 일부 단정적 표현은 근거가 부족합니다.\n"
                "- 누락: 리스크/비용에 대한 언급이 빠져 있습니다.\n"
                "- 모호: '빠르게', '효율적으로' 등 측정 불가한 표현이 있습니다."
            )
        elif role == "verifier":
            body = (
                "검증(모의): 최종에 남길 내용만 선별했습니다.\n"
                "- 유지: 단계적 접근이라는 핵심 골격은 타당합니다.\n"
                "- 제거/표시: 근거 없는 수치는 '확인 필요'로 표시했습니다."
            )
        elif role == "synthesizer":
            body = (
                "최종본(모의): 초안·비판·검증을 종합한 실무용 정리입니다.\n"
                "1. 결론: 목표는 단계적·검증가능한 방식으로 추진합니다.\n"
                "2. 실행: 가설 → 측정 → 보정 순으로 운영합니다.\n"
                "3. 주의: '확인 필요' 항목은 실제 데이터로 확정하세요."
            )
        else:
            body = "모의 응답입니다."

        return f"{header}\n입력 요약: {summary}\n\n{body}"
