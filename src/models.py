"""상가건물 관리비 정산 도메인 모델.

본인 소유 상가건물에서 건물주(관리소장)가 각 임차인(호실)에게
관리비를 청구하는 상황을 가정한다.

- 비용은 공실 포함 전체 호실에 면적/사용량 등으로 배분한다.
- 임차인 호실은 청구 대상, 공실은 건물주 부담(참고)으로 분리한다.
- 상가 관리비는 부가가치세(VAT) 과세 대상이므로 공급가액과 부가세를 구분한다.

외부 의존성 없이 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Dict, List


def round_won(amount: float) -> int:
    """원 단위 반올림(사사오입)."""
    return int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class AllocationMethod(str, Enum):
    """관리비 항목별 배분 방식.

    - AREA('면적')   : 계약(전용)면적 비례 — 일반관리비·청소비·승강기·공용전기 등 대부분
    - EQUAL('호실균등'): 호실 균등 배분
    - USAGE('사용량') : 계량기 사용량 비례 — 호실 전기·수도 등 (검침값 필요)

    모든 방식에서 공실 호실에도 면적분을 산정하되, 그 몫은 건물주 부담으로 분리한다.
    """

    AREA = "면적"
    EQUAL = "호실균등"
    USAGE = "사용량"

    @classmethod
    def from_text(cls, text: str) -> "AllocationMethod":
        text = (text or "").strip()
        aliases = {
            "면적": cls.AREA,
            "면적비례": cls.AREA,
            "면적안분": cls.AREA,
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

    floor: str  # 층
    ho: str  # 호
    area: float  # 계약(전용)면적(m²)
    occupied: bool = True  # 임차(입주) 여부
    tenant: str = ""  # 임차인/상호

    @property
    def key(self) -> str:
        """호실 식별 키 (예: '3-301')."""
        return f"{self.floor}-{self.ho}"

    @property
    def name(self) -> str:
        return f"{self.floor}층 {self.ho}호"


@dataclass
class CostItem:
    """관리비 항목(건물 전체 월 발생 총액, 부가세 제외 공급가액 기준)."""

    name: str
    total: int  # 총액(원)
    method: AllocationMethod

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError(f"'{self.name}' 총액은 음수일 수 없습니다: {self.total}")


@dataclass
class UnitBill:
    """호실별 관리비 산정 결과(공급가액 기준)."""

    unit: Unit
    charges: Dict[str, int] = field(default_factory=dict)  # 항목명 -> 공급가액(원)

    @property
    def supply(self) -> int:
        """공급가액 합계(부가세 제외)."""
        return sum(self.charges.values())


@dataclass
class Settlement:
    """정산 전체 결과.

    임차인 호실은 청구 대상, 공실 호실은 건물주 부담(참고)으로 구분한다.
    """

    bills: List[UnitBill]
    items: List[CostItem]
    vat_rate: float = 0.1  # 부가가치세율 (상가 기본 10%)

    # ---- 부가세 계산 (호실 단위, 임차인만 청구) ----
    def vat(self, bill: UnitBill) -> int:
        """호실 부가세(공급가액 × 세율, 원 단위 반올림)."""
        return round_won(bill.supply * self.vat_rate)

    def billed_total(self, bill: UnitBill) -> int:
        """임차인 청구 합계(공급가액 + 부가세)."""
        return bill.supply + self.vat(bill)

    # ---- 호실 구분 ----
    @property
    def tenant_bills(self) -> List[UnitBill]:
        return [b for b in self.bills if b.unit.occupied]

    @property
    def vacant_bills(self) -> List[UnitBill]:
        return [b for b in self.bills if not b.unit.occupied]

    # ---- 합계 ----
    @property
    def supply_billed_total(self) -> int:
        """임차인 청구 공급가액 합계."""
        return sum(b.supply for b in self.tenant_bills)

    @property
    def vat_total(self) -> int:
        """임차인 부가세 합계."""
        return sum(self.vat(b) for b in self.tenant_bills)

    @property
    def billed_grand_total(self) -> int:
        """임차인 청구 총액(공급가액 + 부가세)."""
        return self.supply_billed_total + self.vat_total

    @property
    def owner_borne_total(self) -> int:
        """공실분 = 건물주 부담 공급가액 합계."""
        return sum(b.supply for b in self.vacant_bills)

    @property
    def building_total(self) -> int:
        """건물 비용 총액(입력 공급가액 기준)."""
        return sum(item.total for item in self.items)

    def item_total_charged(self, item_name: str) -> int:
        return sum(b.charges.get(item_name, 0) for b in self.bills)

    def verify(self) -> List[str]:
        """정산 검증: 항목별 배분합계(임차인+공실)와 입력 총액 일치 확인."""
        problems: List[str] = []
        for item in self.items:
            charged = self.item_total_charged(item.name)
            if charged != item.total:
                problems.append(
                    f"[불일치] {item.name}: 입력 {item.total:,}원 / 배분 {charged:,}원 "
                    f"(차액 {item.total - charged:,}원)"
                )
        # 임차인 청구분 + 건물주 부담분 = 건물 총액
        split = self.supply_billed_total + self.owner_borne_total
        if split != self.building_total:
            problems.append(
                f"[불일치] 공급가액 합계: 건물총액 {self.building_total:,}원 / "
                f"(임차인 {self.supply_billed_total:,} + 공실 {self.owner_borne_total:,}) "
                f"= {split:,}원"
            )
        return problems
