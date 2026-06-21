"""납부 관리: 미납 현황 및 연체료 계산.

payments.csv (호실,납부액,납부일) 와 정산 결과를 대조해
호실별 미납액과 연체료를 산출한다.

연체료 = 미납액 × 연체율(연이율) × 연체일수 ÷ 365  (원 단위 반올림)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from .models import Settlement, round_won

_ENCODING = "utf-8-sig"


@dataclass
class Payment:
    paid: int = 0  # 납부액(원)
    paid_date: Optional[date] = None


@dataclass
class Arrear:
    """호실별 미납/연체 현황."""

    name: str
    billed: int  # 청구액
    paid: int  # 납부액
    overdue_days: int  # 연체일수
    late_fee: int  # 연체료

    @property
    def unpaid(self) -> int:
        return max(self.billed - self.paid, 0)

    @property
    def status(self) -> str:
        if self.paid >= self.billed and self.billed > 0:
            return "완납"
        if self.paid <= 0:
            return "미납"
        return "부분납"

    @property
    def total_due(self) -> int:
        """납부할 총액(미납액 + 연체료)."""
        return self.unpaid + self.late_fee


def _num(text: str) -> int:
    cleaned = (text or "").replace(",", "").replace("원", "").strip()
    return int(round(float(cleaned))) if cleaned else 0


def _parse_date(text: str) -> Optional[date]:
    text = (text or "").strip().replace(".", "-").replace("/", "-")
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def read_payments(path: str) -> Dict[str, Payment]:
    """납부 내역 CSV (호실,납부액,납부일) 를 읽는다."""
    payments: Dict[str, Payment] = {}
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            name = (row.get("호실") or row.get("상호") or "").strip()
            if not name:
                continue
            payments[name] = Payment(
                paid=_num(row.get("납부액") or row.get("입금액") or "0"),
                paid_date=_parse_date(row.get("납부일") or ""),
            )
    return payments


def build_arrears(
    settlement: Settlement,
    payments: Dict[str, Payment],
    due_date: Optional[date] = None,
    late_rate: float = 0.0,
    asof: Optional[date] = None,
) -> List[Arrear]:
    """정산 결과와 납부 내역을 대조해 호실별 미납/연체 현황을 만든다."""
    asof = asof or date.today()
    arrears: List[Arrear] = []
    for bill in settlement.tenant_bills:
        name = bill.unit.name
        billed = settlement.claim(bill)
        pay = payments.get(name, Payment())
        unpaid = max(billed - pay.paid, 0)

        overdue_days = 0
        late_fee = 0
        if unpaid > 0 and due_date is not None and asof > due_date:
            overdue_days = (asof - due_date).days
            if late_rate > 0:
                late_fee = round_won(unpaid * late_rate * overdue_days / 365)

        arrears.append(Arrear(name, billed, pay.paid, overdue_days, late_fee))
    return arrears


def write_arrears(path: str, arrears: List[Arrear]) -> None:
    """미납/연체 현황을 CSV로 저장한다."""
    with open(path, "w", newline="", encoding=_ENCODING) as f:
        w = csv.writer(f)
        w.writerow(["호실", "청구액", "납부액", "미납액", "연체일수", "연체료", "납부할총액", "상태"])
        for a in arrears:
            w.writerow([a.name, a.billed, a.paid, a.unpaid, a.overdue_days,
                        a.late_fee, a.total_due, a.status])
        # 합계
        w.writerow([
            "합계",
            sum(a.billed for a in arrears),
            sum(a.paid for a in arrears),
            sum(a.unpaid for a in arrears),
            "",
            sum(a.late_fee for a in arrears),
            sum(a.total_due for a in arrears),
            "",
        ])
