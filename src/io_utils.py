"""CSV 입출력 유틸리티.

관리소장이 엑셀에서 저장한 CSV(UTF-8 / Excel BOM 모두 허용)를 읽고,
호실별 관리비 고지서를 다시 CSV로 저장한다.

입력 파일 형식
--------------
units.csv  : 층,호,계약면적,임차인,입주여부
costs.csv  : 항목,총액,배분방식
meters.csv : 층,호,항목,사용량   (사용량 비례 항목이 있을 때만 필요)
"""

from __future__ import annotations

import csv
from typing import Dict, List

from .models import AllocationMethod, CostItem, Settlement, Unit

_ENCODING = "utf-8-sig"  # Excel 저장 CSV의 BOM 자동 처리

_TRUE_VALUES = {"y", "yes", "1", "o", "true", "임차", "입주", "예", "유", "거주"}
_FALSE_VALUES = {"n", "no", "0", "x", "false", "공실", "비어있음", "무", "아니오"}


def _parse_won(text: str) -> int:
    """'3,500,000' / '3500000원' 같은 표기를 정수 원으로 변환."""
    cleaned = (text or "").replace(",", "").replace("원", "").strip()
    if not cleaned:
        return 0
    return int(round(float(cleaned)))


def read_units(path: str) -> List[Unit]:
    units: List[Unit] = []
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            if not row or not (row.get("층") or "").strip():
                continue
            tenant = (row.get("임차인") or "").strip()
            occ_raw = (row.get("입주여부") or "").strip().lower()
            if occ_raw in _TRUE_VALUES:
                occupied = True
            elif occ_raw in _FALSE_VALUES:
                occupied = False
            else:
                # 입주여부 미기재 시 임차인명 유무로 판단
                occupied = bool(tenant)
            units.append(
                Unit(
                    floor=row["층"].strip(),
                    ho=(row.get("호") or "").strip(),
                    area=float((row.get("계약면적") or "0").replace(",", "").strip()),
                    occupied=occupied,
                    tenant=tenant,
                )
            )
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
            items.append(
                CostItem(
                    name=name,
                    total=_parse_won(row.get("총액", "0")),
                    method=AllocationMethod.from_text(row.get("배분방식", "")),
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
            floor = (row.get("층") or "").strip()
            ho = (row.get("호") or "").strip()
            item = (row.get("항목") or "").strip()
            if not (floor and ho and item):
                continue
            key = f"{floor}-{ho}"
            amount = float((row.get("사용량") or "0").replace(",", "").strip())
            usage.setdefault(key, {})[item] = amount
    return usage


def write_bills(path: str, settlement: Settlement) -> None:
    """호실별 고지서를 CSV로 저장한다.

    임차인 호실: 항목별 공급가액 + 공급가액합계 + 부가세 + 청구합계
    공실 호실  : 건물주 부담분(공급가액)만 표기, 부가세/청구합계는 '-'
    """
    item_names = [item.name for item in settlement.items]
    header = [
        "층", "호", "임차인", "계약면적", "상태",
        *item_names,
        "공급가액", "부가세", "청구합계",
    ]

    with open(path, "w", newline="", encoding=_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # 임차인 호실 먼저, 공실 나중
        for bill in [*settlement.tenant_bills, *settlement.vacant_bills]:
            u = bill.unit
            if u.occupied:
                vat = settlement.vat(bill)
                writer.writerow(
                    [u.floor, u.ho, u.tenant, u.area, "임차",
                     *[bill.charges.get(n, 0) for n in item_names],
                     bill.supply, vat, settlement.billed_total(bill)]
                )
            else:
                writer.writerow(
                    [u.floor, u.ho, u.tenant, u.area, "공실(건물주부담)",
                     *[bill.charges.get(n, 0) for n in item_names],
                     bill.supply, "-", "-"]
                )

        # 합계 행
        writer.writerow([])
        writer.writerow(
            ["임차인 청구 합계", "", "", "", "",
             *[sum(b.charges.get(n, 0) for b in settlement.tenant_bills) for n in item_names],
             settlement.supply_billed_total, settlement.vat_total, settlement.billed_grand_total]
        )
        writer.writerow(
            ["건물주 부담(공실)", "", "", "", "",
             *[sum(b.charges.get(n, 0) for b in settlement.vacant_bills) for n in item_names],
             settlement.owner_borne_total, "-", "-"]
        )
        writer.writerow(
            ["건물 총액(검증)", "", "", "", "",
             *[settlement.item_total_charged(n) for n in item_names],
             settlement.building_total, "", ""]
        )
