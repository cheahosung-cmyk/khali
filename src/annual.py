"""연간 집계표 생성.

여러 달의 고지서 CSV(write_bills 출력)를 모아 호실별·월별 청구액과
연간 합계를 한 표로 만든다.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List, Tuple

from .io_utils import read_prev_totals

_ENCODING = "utf-8-sig"


def _label(path: str) -> str:
    """파일명에서 월 라벨을 만든다 (예: bills_2024_12.csv -> 2024_12)."""
    base = os.path.splitext(os.path.basename(path))[0]
    for prefix in ("bills_", "bills-", "정산_", "고지서_"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def aggregate(paths: List[str]) -> Tuple[List[str], Dict[str, Dict[str, int]]]:
    """월별 고지서들을 읽어 (월 라벨 목록, {호실: {월: 청구액}}) 로 집계한다."""
    labels: List[str] = []
    table: Dict[str, Dict[str, int]] = {}
    for path in paths:
        label = _label(path)
        labels.append(label)
        totals = read_prev_totals(path)
        for name, amount in totals.items():
            table.setdefault(name, {})[label] = amount
    return labels, table


def write_annual(path: str, paths: List[str]) -> None:
    """연간 집계표를 CSV로 저장한다."""
    labels, table = aggregate(paths)

    # 호실 순서: 첫 등장 순서 유지
    names: List[str] = list(table.keys())

    with open(path, "w", newline="", encoding=_ENCODING) as f:
        w = csv.writer(f)
        w.writerow(["호실", *labels, "연간합계"])
        for name in names:
            row = [table[name].get(l, 0) for l in labels]
            w.writerow([name, *row, sum(row)])
        # 월합계 행
        month_totals = [sum(table[n].get(l, 0) for n in names) for l in labels]
        w.writerow(["월합계", *month_totals, sum(month_totals)])
