"""신호 후처리 필터 (전략과 무관하게 공통 적용)."""

from __future__ import annotations

from .base import Action, Signal
from .indicators import sma


def apply_trend_filter(
    signal: Signal, closes: list[float], ma_period: int
) -> Signal:
    """추세 필터: 가격이 N봉 이동평균 아래면 신규 매수를 막는다.

    하락 추세에서 '저점 매수' 신호를 무시해 큰 손실을 피한다. 매도/홀드는
    그대로 통과시킨다(청산은 리스크 매니저가 담당).
    """
    if ma_period <= 0 or signal.action != Action.BUY:
        return signal
    ma = sma(closes, ma_period)
    if ma is None:
        return signal
    if closes[-1] < ma:
        return Signal(
            Action.HOLD,
            f"추세필터: 가격 {closes[-1]:.1f} < MA{ma_period} {ma:.1f}",
        )
    return signal
