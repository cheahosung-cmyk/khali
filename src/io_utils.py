"""CSV 입출력 유틸리티.

관리소장이 엑셀에서 그대로 저장한 CSV(UTF-8 / Excel BOM 모두 허용)를
읽고, 세대별 고지서를 다시 CSV로 저장한다.

입력 파일 형식
--------------
units.csv   : 동,호,전용면적,입주여부
costs.csv   : 항목,총액,배분방식
meters.csv  : 동,호,항목,사용량   (사용량 비례 항목이 있을 때만 필요)
"""

from __future__ import annotations

import csv
from typing import Dict, List

from .models import AllocationMethod, CostItem, Settlement, Unit

# Excel 저장 CSV의 BOM을 자동 처리
_ENCODING = "utf-8-sig"

_TRUE_VALUES = {"y", "yes", "1", "o", "true", "입주", "거주", "예", "유"}


def _parse_won(text: str) -> int:
    """'3,500,000' / '3500000원' 같은 표기를 정수 원으로 변환."""
    cleaned = (text or "").replace(",", "").replace("원", "").strip()
    if not cleaned:
        return 0
    return int(round(float(cleaned)))


def _parse_bool(text: str) -> bool:
    return (text or "").strip().lower() in _TRUE_VALUES


def read_units(path: str) -> List[Unit]:
    units: List[Unit] = []
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            if not row or not (row.get("동") or "").strip():
                continue
            units.append(
                Unit(
                    dong=row["동"].strip(),
                    ho=row["호"].strip(),
                    area=float((row.get("전용면적") or "0").replace(",", "").strip()),
                    occupied=_parse_bool(row.get("입주여부", "Y")),
                )
            )
    if not units:
        raise ValueError(f"세대 정보를 읽지 못했습니다: {path}")
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
    """검침값을 {세대키: {항목명: 사용량}} 형태로 읽는다."""
    usage: Dict[str, Dict[str, float]] = {}
    with open(path, newline="", encoding=_ENCODING) as f:
        for row in csv.DictReader(f):
            dong = (row.get("동") or "").strip()
            ho = (row.get("호") or "").strip()
            item = (row.get("항목") or "").strip()
            if not (dong and ho and item):
                continue
            key = f"{dong}-{ho}"
            amount = float((row.get("사용량") or "0").replace(",", "").strip())
            usage.setdefault(key, {})[item] = amount
    return usage


def write_bills(path: str, settlement: Settlement) -> None:
    """세대별 고지서를 CSV로 저장한다(항목별 컬럼 + 합계)."""
    item_names = [item.name for item in settlement.items]
    header = ["동", "호", "전용면적", "입주여부", *item_names, "합계"]

    with open(path, "w", newline="", encoding=_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for bill in settlement.bills:
            u = bill.unit
            writer.writerow(
                [
                    u.dong,
                    u.ho,
                    u.area,
                    "Y" if u.occupied else "N",
                    *[bill.charges.get(name, 0) for name in item_names],
                    bill.total,
                ]
            )
        # 합계 행
        writer.writerow(
            [
                "합계",
                "",
                "",
                "",
                *[settlement.item_total_charged(name) for name in item_names],
                settlement.grand_total,
            ]
        )
