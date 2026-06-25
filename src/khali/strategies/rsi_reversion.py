"""RSI 평균회귀 전략.

RSI 과매도(<oversold) 구간 진입 -> 매수,
과매수(>overbought) 또는 중립 회복 -> 매도.
"""

from __future__ import annotations

from .base import Action, Signal, Strategy, StrategyContext
from .indicators import rsi
from .registry import register


@register("rsi_reversion")
class RSIReversion(Strategy):
    def __init__(
        self,
        period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
        **params,
    ):
        super().__init__(
            period=period, oversold=oversold, overbought=overbought, **params
        )
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def min_candles(self) -> int:
        return self.period + 2

    @staticmethod
    def param_grid() -> dict[str, list]:
        return {
            "period": [7, 14, 21],
            "oversold": [20, 25, 30, 35],
            "overbought": [65, 70, 75, 80],
        }

    def generate_signal(self, ctx: StrategyContext) -> Signal:
        closes = [c.close for c in ctx.candles]
        value = rsi(closes, self.period)
        if value is None:
            return Signal(Action.HOLD, "데이터 부족")

        if value < self.oversold and not ctx.has_position:
            return Signal(Action.BUY, f"RSI 과매도 {value:.1f}")
        if value > self.overbought and ctx.has_position:
            return Signal(Action.SELL, f"RSI 과매수 {value:.1f}")
        return Signal(Action.HOLD, f"RSI {value:.1f}")
