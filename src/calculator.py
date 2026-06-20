"""상가건물 관리비 정산 엔진.

핵심 원칙
---------
1. 모든 배분은 '가중치 기반 최대잉여법(largest remainder method)'으로 통일한다.
   - 면적     : 가중치 = 계약면적
   - 호실균등  : 가중치 = 1 (전 호실)
   - 사용량   : 가중치 = 검침 사용량
2. 공실 포함 전체 호실에 배분한 뒤, 임차인 몫은 청구·공실 몫은 건물주 부담으로
   분리한다. (공실 부담을 임차인에게 전가하지 않음)
3. 원(₩) 단위 잔여를 소수부가 큰 호실부터 배분해
   '항목별 배분 합계 = 항목 총액'이 항상 정확히 일치하도록 보장한다.
"""

from __future__ import annotations

from typing import Dict, List, Mapping

from .models import (
    AllocationMethod,
    CostItem,
    Settlement,
    Unit,
    UnitBill,
)

# 호실 키 -> {항목명 -> 사용량}
UsageTable = Mapping[str, Mapping[str, float]]


def allocate(total_won: int, weights: Dict[str, float]) -> Dict[str, int]:
    """총액(원)을 가중치에 따라 정수 원 단위로 배분한다(최대잉여법).

    반환 값들의 합은 항상 total_won 과 정확히 일치한다.
    """
    keys = list(weights.keys())
    if not keys:
        return {}

    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        return {k: 0 for k in keys}

    raw = {k: total_won * weights[k] / weight_sum for k in keys}
    floored = {k: int(raw[k]) for k in keys}
    remainder = total_won - sum(floored.values())

    by_frac = sorted(keys, key=lambda k: raw[k] - floored[k], reverse=True)
    for i in range(remainder):
        floored[by_frac[i % len(by_frac)]] += 1

    return floored


def _weights_for(
    item: CostItem,
    units: List[Unit],
    usage: UsageTable,
) -> Dict[str, float]:
    """항목의 배분방식에 따른 호실별 가중치(공실 포함)를 계산한다."""
    method = item.method
    weights: Dict[str, float] = {}

    for u in units:
        if method is AllocationMethod.AREA:
            weights[u.key] = u.area
        elif method is AllocationMethod.EQUAL:
            weights[u.key] = 1.0
        elif method is AllocationMethod.USAGE:
            weights[u.key] = float(usage.get(u.key, {}).get(item.name, 0.0))
        else:  # pragma: no cover
            raise ValueError(f"지원하지 않는 배분방식: {method}")

    return weights


def settle(
    units: List[Unit],
    items: List[CostItem],
    usage: UsageTable | None = None,
    vat_rate: float = 0.1,
) -> Settlement:
    """호실 / 비용항목 / 검침값을 받아 호실별 관리비를 산정한다."""
    if not units:
        raise ValueError("호실 정보가 비어 있습니다.")

    usage = usage or {}
    bills = {u.key: UnitBill(unit=u) for u in units}

    for item in items:
        weights = _weights_for(item, units, usage)
        allocation = allocate(item.total, weights)
        for key, amount in allocation.items():
            bills[key].charges[item.name] = amount

    ordered = [bills[u.key] for u in units]
    return Settlement(bills=ordered, items=list(items), vat_rate=vat_rate)
