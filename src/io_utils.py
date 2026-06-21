"""CSV 입출력 유틸리티.

관리소장이 엑셀에서 저장한 CSV(UTF-8 / Excel BOM 모두 허용)를 읽고,
호실별 관리비 고지서를 다시 CSV로 저장한다.

입력 파일 형식
--------------
units.csv  : 호실,평수,입주여부
costs.csv  : 항목,총액,배분방식,단가      (단가는 선택)
meters.csv : 호실,항목,사용량            (사용량 비례 항목이 있을 때만 필요)
"""

from __future__ import annotations

import csv
from typing import Dict, List, Optional

from .models import AllocationMethod, CostItem, Settlement, Unit

_ENCODING = "utf-8-sig"  # Excel 저장 CSV의 BOM 자동 처리

_TRUE_VALUES = {"y", "yes", "1", "o", "true", "임차", "입주", "예", "유", "거주"}
_FALSE_VALUES = {"n", "no", "0", "x", "false", "공실", "비어있음", "무", "아니오"}


def _num(text: str) -> float:
    cleaned = (text or "").replace(",", "").replace("원", "").strip()
    return float(cleaned) if cleaned else 0.0


def _parse_won(text: str) -> int:
    return int(round(_num(text)))


def read_units(path: str) -> List[Unit]:
    units: List[Unit] = []
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            name = (row.get("호실") or row.get("상호") or "").strip()
            if not name:
                continue
            area = _num(row.get("평수") or row.get("분양평수") or row.get("면적") or "0")
            occ_raw = (row.get("입주여부") or "").strip().lower()
            if occ_raw in _TRUE_VALUES:
                occupied = True
            elif occ_raw in _FALSE_VALUES:
                occupied = False
            else:
                occupied = True  # 미기재 시 임차로 간주
            units.append(Unit(name=name, area=area, occupied=occupied))
    if not units:
        raise ValueError(f"호실 정보를 읽지 못했습니다: {path}")
    return units


def read_costs(path: str) -> List[CostItem]:
    items: List[CostItem] = []
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            name = (row.get("항목") or "").strip()
            if not name:
                continue
            rate_raw = (row.get("단가") or "").strip()
            rate: Optional[float] = _num(rate_raw) if rate_raw else None
            items.append(
                CostItem(
                    name=name,
                    total=_parse_won(row.get("총액", "0")),
                    method=AllocationMethod.from_text(row.get("배분방식", "")),
                    rate=rate,
                )
            )
    if not items:
        raise ValueError(f"비용 항목을 읽지 못했습니다: {path}")
    return items


def read_meters(path: str) -> Dict[str, Dict[str, float]]:
    """검침값을 {호실키: {항목명: 사용량}} 형태로 읽는다."""
    usage: Dict[str, Dict[str, float]] = {}
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            name = (row.get("호실") or row.get("상호") or "").strip()
            item = (row.get("항목") or "").strip()
            if not (name and item):
                continue
            usage.setdefault(name, {})[item] = _num(row.get("사용량") or "0")
    return usage


def read_prev_totals(path: str) -> Dict[str, int]:
    """이전 달 고지서 CSV(write_bills 출력)에서 호실별 청구액을 읽는다.

    전월 대비 증감 표시에 사용한다. {호실명: 청구액}.
    """
    totals: Dict[str, int] = {}
    with open(path, newline="", encoding=_ENCODING) as f:
        rows = list(csv.reader(f))
    if not rows:
        return totals
    header = rows[0]
    idx = None
    for col in ("청구합계", "합계"):
        if col in header:
            idx = header.index(col)
            break
    if idx is None:
        idx = len(header) - 1
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        name = r[0].strip()
        if any(k in name for k in ("합계", "총액", "부담", "검증")):
            continue
        try:
            totals[name] = int(float(r[idx].replace(",", "").strip()))
        except (ValueError, IndexError):
            continue
    return totals


def write_bills(path: str, settlement: Settlement,
                prev: Optional[Dict[str, int]] = None) -> None:
    """호실별 고지서를 CSV로 저장한다.

    - 부가세 적용 시: 항목별 + 공급가액 + 부가세 + 청구합계
    - 부가세 미적용 시: 항목별 + 합계
    - 공실 호실은 건물주 부담분을 별도 표시
    - prev(전월 청구액)가 있으면 전월합계/증감 컬럼을 추가
    """
    item_names = [item.name for item in settlement.items]
    use_vat = settlement.vat_rate > 0
    use_status = settlement.has_vacant
    use_prev = prev is not None

    header = ["호실", "평수"]
    if use_status:
        header.append("상태")
    header += item_names
    if use_vat:
        header += ["공급가액", "부가세", "청구합계"]
    else:
        header += ["합계"]
    if use_prev:
        header += ["전월합계", "증감"]

    def _row(bill, status_label=None):
        u = bill.unit
        row = [u.name, u.area]
        if use_status:
            row.append(status_label)
        row += [bill.charges.get(n, 0) for n in item_names]
        if use_vat:
            if u.occupied:
                row += [bill.supply, settlement.vat(bill), settlement.billed_total(bill)]
            else:
                row += [bill.supply, "-", "-"]
        else:
            row += [bill.supply]
        if use_prev:
            if u.occupied and u.name in prev:
                pv = prev[u.name]
                row += [pv, settlement.claim(bill) - pv]
            else:
                row += ["", ""]
        return row

    with open(path, "w", newline="", encoding=_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for bill in settlement.tenant_bills:
            writer.writerow(_row(bill, "임차"))
        for bill in settlement.vacant_bills:
            writer.writerow(_row(bill, "공실(건물주부담)"))

        # 합계 행
        writer.writerow([])
        prefix = ["임차인 합계", ""]
        if use_status:
            prefix.append("")
        tail = [sum(b.charges.get(n, 0) for b in settlement.tenant_bills) for n in item_names]
        if use_vat:
            tail += [settlement.supply_billed_total, settlement.vat_total, settlement.billed_grand_total]
        else:
            tail += [settlement.supply_billed_total]
        if use_prev:
            prev_sum = sum(prev.get(b.unit.name, 0) for b in settlement.tenant_bills)
            cur_sum = sum(settlement.claim(b) for b in settlement.tenant_bills if b.unit.name in prev)
            tail += [prev_sum, cur_sum - prev_sum]
        writer.writerow(prefix + tail)

        if settlement.has_vacant:
            vp = ["건물주 부담(공실)", ""]
            if use_status:
                vp.append("")
            vtail = [sum(b.charges.get(n, 0) for b in settlement.vacant_bills) for n in item_names]
            if use_vat:
                vtail += [settlement.owner_borne_total, "-", "-"]
            else:
                vtail += [settlement.owner_borne_total]
            if use_prev:
                vtail += ["", ""]
            writer.writerow(vp + vtail)

        bp = ["건물 총액(검증)", ""]
        if use_status:
            bp.append("")
        btail = [settlement.item_total_charged(n) for n in item_names]
        if use_vat:
            btail += [settlement.building_total, "", ""]
        else:
            btail += [settlement.building_total]
        if use_prev:
            btail += ["", ""]
        writer.writerow(bp + btail)
