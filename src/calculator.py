"""관리비 정산 엔진.

핵심 원칙
---------
1. 모든 배분은 '가중치 기반 최대잉여법(largest remainder method)'으로 통일한다.
   - 면적   : 가중치 = 전용면적
   - 세대균등: 가중치 = 1 (전 세대)
   - 입주균등: 가중치 = 1 (입주 세대만)
   - 사용량 : 가중치 = 검침 사용량
2. 원(₩) 단위 정수로 떨어지도록 반올림하되, 1원 단위 잔여를 소수부가 큰 세대부터
   배분해 '세대별 청구 합계 = 항목 총액'이 항상 정확히 일치하도록 보장한다.
   (실무 정산에서 합계 1~2원이 안 맞는 사고를 원천 차단)
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

# (동, 호) 단위 키 -> {항목명 -> 사용량}
UsageTable = Mapping[str, Mapping[str, float]]


def allocate(total_won: int, weights: Dict[str, float]) -> Dict[str, int]:
    """총액(원)을 가중치에 따라 정수 원 단위로 배분한다(최대잉여법).

    반환된 값들의 합은 항상 total_won 과 정확히 일치한다.
    """
    keys = list(weights.keys())
    if not keys:
        return {}

    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        # 가중치가 없으면(예: 사용량 0) 아무에게도 부과하지 않는다.
        return {k: 0 for k in keys}

    raw = {k: total_won * weights[k] / weight_sum for k in keys}
    floored = {k: int(raw[k]) for k in keys}  # 내림
    remainder = total_won - sum(floored.values())

    # 소수부가 큰 세대부터 1원씩 잔여 배분
    by_frac = sorted(keys, key=lambda k: raw[k] - floored[k], reverse=True)
    for i in range(remainder):
        floored[by_frac[i % len(by_frac)]] += 1

    return floored


def _weights_for(
    item: CostItem,
    units: List[Unit],
    usage: UsageTable,
) -> Dict[str, float]:
    """항목의 배분방식에 따른 세대별 가중치를 계산한다."""
    method = item.method
    weights: Dict[str, float] = {}

    for u in units:
        if method is AllocationMethod.AREA:
            weights[u.key] = u.area
        elif method is AllocationMethod.EQUAL:
            weights[u.key] = 1.0
        elif method is AllocationMethod.OCCUPIED:
            weights[u.key] = 1.0 if u.occupied else 0.0
        elif method is AllocationMethod.USAGE:
            weights[u.key] = float(usage.get(u.key, {}).get(item.name, 0.0))
        else:  # pragma: no cover - Enum이 모든 경우를 보장
            raise ValueError(f"지원하지 않는 배분방식: {method}")

    return weights


def settle(
    units: List[Unit],
    items: List[CostItem],
    usage: UsageTable | None = None,
) -> Settlement:
    """세대 / 비용항목 / 검침값을 받아 세대별 고지서를 산출한다."""
    if not units:
        raise ValueError("세대 정보가 비어 있습니다.")

    usage = usage or {}
    bills = {u.key: UnitBill(unit=u) for u in units}

    for item in items:
        weights = _weights_for(item, units, usage)
        allocation = allocate(item.total, weights)
        for key, amount in allocation.items():
            bills[key].charges[item.name] = amount

    # 입력 순서를 유지해 고지서 출력
    ordered = [bills[u.key] for u in units]
    return Settlement(bills=ordered, items=list(items))
