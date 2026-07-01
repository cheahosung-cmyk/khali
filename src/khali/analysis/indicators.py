"""공용 기술지표 헬퍼.

여러 전략이 동일한 True Range / 이동평균 공식을 각자 재구현하던 것을 한곳으로
모은다. True Range는 3항 max와 전일 종가 의존성 때문에 미묘하게 틀리기 쉬워,
단일 정의를 유지하는 것이 중요하다.
"""

from __future__ import annotations

from typing import Iterable, Sized


def true_range(high: float, low: float, prev_close: float) -> float:
    """당일 True Range = max(고저폭, |고가-전일종가|, |저가-전일종가|)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def sma(values: Sized | Iterable[float], window: int) -> float | None:
    """단순이동평균. 표본이 window 미만이면 None.

    values는 보통 최근 window개만 담은 deque이므로 전체 평균을 그대로 쓴다.
    """
    seq = list(values)
    if len(seq) < window:
        return None
    return sum(seq) / len(seq)
