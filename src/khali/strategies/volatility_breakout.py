"""변동성 돌파 전략 (래리 윌리엄스 방식).

목표가 = 당일 시가 + (전일 고가 - 전일 저가) * k
현재가가 목표가를 돌파하면 매수. 보유 중 다음 캔들 시작/청산 신호에 매도.
단기 변동성 추세를 잡는, 백테스트로 검증하기 쉬운 대표적 전략이다.
"""

from __future__ import annotations

from .base import Action, Signal, Strategy, StrategyContext
from .registry import register


@register("volatility_breakout")
class VolatilityBreakout(Strategy):
    def __init__(self, k: float = 0.5, **params):
        super().__init__(k=k, **params)
        self.k = k

    def min_candles(self) -> int:
        return 3

    def generate_signal(self, ctx: StrategyContext) -> Signal:
        if len(ctx.candles) < 2:
            return Signal(Action.HOLD, "데이터 부족")

        prev = ctx.candles[-2]
        cur = ctx.candles[-1]
        rng = prev.high - prev.low
        target = cur.open + rng * self.k

        if not ctx.has_position and cur.close >= target and rng > 0:
            return Signal(
                Action.BUY,
                f"변동성 돌파 (목표 {target:.2f} 도달, k={self.k})",
            )
        # 보유 중이면 청산은 리스크 매니저(손절/익절/트레일링)가 담당.
        # 추가로, 돌파 실패로 시가 밑으로 깨지면 회피 매도.
        if ctx.has_position and cur.close < cur.open:
            return Signal(Action.SELL, "시가 하회 청산")
        return Signal(Action.HOLD, f"목표 {target:.2f}")
