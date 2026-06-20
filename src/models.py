"""상가건물 관리비 정산 도메인 모델.

웰스타임 빌딩처럼 건물주(관리소장)가 각 호실(임차인)에게 관리비를
청구하는 상황을 가정한다.

- 호실은 상호명으로 식별하고, 면적은 분양평수(평)를 기준으로 한다.
- 비용은 항목별 배분방식(면적 / 호실균등 / 사용량)으로 배분한다.
- 일반관리비처럼 '평당 단가'가 정해진 항목은 단가×평수로 정액 산정한다.
- 공실 호실의 면적분은 산정하되 건물주 부담(참고)으로 분리한다.
- 부가세는 선택(기본 미적용). 적용 시 공급가액/부가세/청구합계를 구분한다.

외부 의존성 없이 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Dict, List, Optional


def round_won(amount: float) -> int:
    """원 단위 반올림(사사오입)."""
    return int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class AllocationMethod(str, Enum):
    """관리비 항목별 배분 방식.

    - AREA('면적')   : 분양평수 비례 — 일반관리비·공동전기·공용수도 등 대부분
    - EQUAL('호실균등'): 호실 균등 배분
    - USAGE('사용량') : 계량기 검침 사용량 비례 — 세대 수도 등 (검침값 필요)
    """

    AREA = "면적"
    EQUAL = "호실균등"
    USAGE = "사용량"

    @classmethod
    def from_text(cls, text: str) -> "AllocationMethod":
        text = (text or "").strip()
        aliases = {
            "면적": cls.AREA,
            "평수": cls.AREA,
            "면적비례": cls.AREA,
            "분배율": cls.AREA,
            "호실균등": cls.EQUAL,
            "균등": cls.EQUAL,
            "호실": cls.EQUAL,
            "사용량": cls.USAGE,
            "사용량비례": cls.USAGE,
            "검침": cls.USAGE,
        }
        if text in aliases:
            return aliases[text]
        raise ValueError(
            f"알 수 없는 배분방식: '{text}'. 사용 가능: 면적 / 호실균등 / 사용량"
        )


@dataclass(frozen=True)
class Unit:
    """호실(점포/사무실) 정보."""

    name: str  # 호실/상호 (식별자, 예: '원유로', '카카오3F')
    area: float  # 분양평수(평)
    occupied: bool = True  # 임차(입주) 여부

    @property
    def key(self) -> str:
        return self.name


@dataclass
class CostItem:
    """관리비 항목.

    - rate 가 지정되면 '단가 × 가중치(평수/사용량/호실)'로 정액 산정하고
      total 은 그 합으로 자동 계산된다. (예: 일반관리비 = 평수 × 4,000원)
    - rate 가 없으면 total 을 배분방식에 따라 나눈다.
    """

    name: str
    total: int  # 총액(원). 단가 방식이면 0으로 두면 자동 산출됨
    method: AllocationMethod
    rate: Optional[float] = None  # 단가(원/평 또는 원/사용단위)

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError(f"'{self.name}' 총액은 음수일 수 없습니다: {self.total}")


@dataclass
class UnitBill:
    """호실별 관리비 산정 결과."""

    unit: Unit
    charges: Dict[str, int] = field(default_factory=dict)  # 항목명 -> 금액(원)

    @property
    def supply(self) -> int:
        """공급가액 합계(부가세 제외)."""
        return sum(self.charges.values())


@dataclass
class Settlement:
    """정산 전체 결과."""

    bills: List[UnitBill]
    items: List[CostItem]
    vat_rate: float = 0.0  # 부가가치세율 (기본 미적용)

    # ---- 부가세 ----
    def vat(self, bill: UnitBill) -> int:
        return round_won(bill.supply * self.vat_rate)

    def billed_total(self, bill: UnitBill) -> int:
        return bill.supply + self.vat(bill)

    # ---- 호실 구분 ----
    @property
    def tenant_bills(self) -> List[UnitBill]:
        return [b for b in self.bills if b.unit.occupied]

    @property
    def vacant_bills(self) -> List[UnitBill]:
        return [b for b in self.bills if not b.unit.occupied]

    @property
    def has_vacant(self) -> bool:
        return any(not b.unit.occupied for b in self.bills)

    # ---- 합계 ----
    @property
    def supply_billed_total(self) -> int:
        return sum(b.supply for b in self.tenant_bills)

    @property
    def vat_total(self) -> int:
        return sum(self.vat(b) for b in self.tenant_bills)

    @property
    def billed_grand_total(self) -> int:
        return self.supply_billed_total + self.vat_total

    @property
    def owner_borne_total(self) -> int:
        """공실분 = 건물주 부담 합계."""
        return sum(b.supply for b in self.vacant_bills)

    @property
    def building_total(self) -> int:
        return sum(item.total for item in self.items)

    def item_total_charged(self, item_name: str) -> int:
        return sum(b.charges.get(item_name, 0) for b in self.bills)

    def verify(self) -> List[str]:
        """정산 검증: 항목별 배분합계와 총액, 임차인+공실=건물총액 일치 확인."""
        problems: List[str] = []
        for item in self.items:
            charged = self.item_total_charged(item.name)
            if charged != item.total:
                problems.append(
                    f"[불일치] {item.name}: 총액 {item.total:,}원 / 배분 {charged:,}원 "
                    f"(차액 {item.total - charged:,}원)"
                )
        split = self.supply_billed_total + self.owner_borne_total
        if split != self.building_total:
            problems.append(
                f"[불일치] 합계: 건물총액 {self.building_total:,}원 / "
                f"(임차인 {self.supply_billed_total:,} + 공실 {self.owner_borne_total:,}) "
                f"= {split:,}원"
            )
        return problems
