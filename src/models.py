"""관리비 정산 도메인 모델.

외부 의존성 없이 표준 라이브러리(dataclasses)만 사용해
관리소장이 별도 설치 없이도 바로 실행할 수 있도록 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class AllocationMethod(str, Enum):
    """관리비 항목별 배분 방식.

    - AREA('면적')        : 전용면적 비례 배분 (일반관리비·청소비·장기수선충당금 등)
    - EQUAL('세대균등')    : 전 세대 균등 배분
    - OCCUPIED('입주균등') : 입주(거주) 세대만 균등 배분 (공실 제외)
    - USAGE('사용량')      : 계량기 사용량 비례 배분 (세대 전기·수도·가스·난방 등)
    """

    AREA = "면적"
    EQUAL = "세대균등"
    OCCUPIED = "입주균등"
    USAGE = "사용량"

    @classmethod
    def from_text(cls, text: str) -> "AllocationMethod":
        text = (text or "").strip()
        # 흔히 쓰는 표기 흡수
        aliases = {
            "면적": cls.AREA,
            "면적비례": cls.AREA,
            "면적안분": cls.AREA,
            "세대균등": cls.EQUAL,
            "균등": cls.EQUAL,
            "세대": cls.EQUAL,
            "입주균등": cls.OCCUPIED,
            "입주": cls.OCCUPIED,
            "거주균등": cls.OCCUPIED,
            "사용량": cls.USAGE,
            "사용량비례": cls.USAGE,
            "검침": cls.USAGE,
        }
        if text in aliases:
            return aliases[text]
        raise ValueError(
            f"알 수 없는 배분방식: '{text}'. "
            f"사용 가능: 면적 / 세대균등 / 입주균등 / 사용량"
        )


@dataclass(frozen=True)
class Unit:
    """세대(호) 정보."""

    dong: str  # 동
    ho: str  # 호
    area: float  # 전용면적(m²)
    occupied: bool = True  # 입주(거주) 여부

    @property
    def key(self) -> str:
        """세대 식별 키 (예: '101-1502')."""
        return f"{self.dong}-{self.ho}"

    @property
    def name(self) -> str:
        return f"{self.dong}동 {self.ho}호"


@dataclass
class CostItem:
    """관리비 항목(건물 전체 월 발생 총액)."""

    name: str  # 항목명 (예: 일반관리비)
    total: int  # 총액(원)
    method: AllocationMethod  # 배분방식

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError(f"'{self.name}' 총액은 음수일 수 없습니다: {self.total}")


@dataclass
class UnitBill:
    """세대별 고지서(정산 결과)."""

    unit: Unit
    charges: Dict[str, int] = field(default_factory=dict)  # 항목명 -> 금액(원)

    @property
    def total(self) -> int:
        return sum(self.charges.values())


@dataclass
class Settlement:
    """정산 전체 결과."""

    bills: List[UnitBill]
    items: List[CostItem]

    @property
    def grand_total(self) -> int:
        """세대 청구 합계(= 건물 비용 총액과 일치해야 함)."""
        return sum(b.total for b in self.bills)

    def item_total_charged(self, item_name: str) -> int:
        return sum(b.charges.get(item_name, 0) for b in self.bills)

    def verify(self) -> List[str]:
        """정산 검증: 항목별 청구합계와 입력 총액이 일치하는지 확인.

        불일치 항목 메시지 리스트를 반환한다(빈 리스트면 정상).
        """
        problems: List[str] = []
        for item in self.items:
            charged = self.item_total_charged(item.name)
            if charged != item.total:
                problems.append(
                    f"[불일치] {item.name}: 입력 {item.total:,}원 / 청구 {charged:,}원 "
                    f"(차액 {item.total - charged:,}원)"
                )
        return problems
