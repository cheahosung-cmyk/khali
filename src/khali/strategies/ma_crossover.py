"""이동평균 교차 추세추종 전략.

단기 이평이 장기 이평을 상향 돌파(골든크로스) -> 매수,
하향 돌파(데드크로스) -> 매도.
"""

from __future__ import annotations

from .base import Action, Signal, Strategy, StrategyContext
from .indicators import sma
from .registry import register


@register("ma_crossover")
class MACrossover(Strategy):
    def __init__(self, short: int = 10, long: int = 30, **params):
        super().__init__(short=short, long=long, **params)
        self.short = short
        self.long = long

    def min_candles(self) -> int:
        return self.long + 2

    def generate_signal(self, ctx: StrategyContext) -> Signal:
        closes = [c.close for c in ctx.candles]
        if len(closes) < self.long + 1:
            return Signal(Action.HOLD, "데이터 부족")

        short_now = sma(closes, self.short)
        long_now = sma(closes, self.long)
        short_prev = sma(closes[:-1], self.short)
        long_prev = sma(closes[:-1], self.long)
        if None in (short_now, long_now, short_prev, long_prev):
            return Signal(Action.HOLD, "지표 계산불가")

        golden = short_prev <= long_prev and short_now > long_now
        dead = short_prev >= long_prev and short_now < long_now

        if golden and not ctx.has_position:
            return Signal(Action.BUY, f"골든크로스 {self.short}>{self.long}")
        if dead and ctx.has_position:
            return Signal(Action.SELL, f"데드크로스 {self.short}<{self.long}")
        return Signal(Action.HOLD, "교차 없음")
