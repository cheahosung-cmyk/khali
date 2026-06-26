"""이동평균 크로스 전략 (전략 2번 후보).

가장 고전적인 추세추종. 단기 이동평균이 장기 이동평균을 상향 돌파(골든
크로스)하면 매수, 하향 돌파(데드 크로스)하면 청산. 오버나잇 보유.

룩어헤드 차단: 크로스 판정은 직전 봉까지 완료된 종가의 이동평균으로 한다.
"""

from __future__ import annotations

from collections import deque

from khali.models import Bar, Position, Side, Signal
from khali.strategy.base import Strategy


class MACrossover(Strategy):
    name = "ma_crossover"

    def __init__(self, fast: int = 10, slow: int = 30):
        if fast >= slow:
            raise ValueError("fast는 slow보다 작아야 합니다")
        self.fast = fast
        self.slow = slow
        self._closes: deque[float] = deque(maxlen=slow)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def warmup(self) -> int:
        return self.slow + 1

    def _ma(self, n: int) -> float | None:
        if len(self._closes) < n:
            return None
        # deque의 최근 n개 평균
        vals = list(self._closes)[-n:]
        return sum(vals) / n

    def on_bar(self, bar: Bar, position: Position) -> list[Signal]:
        signals: list[Signal] = []
        # 오늘 종가를 반영한 '현재' MA와, 직전 봉에서 저장한 '이전' MA를 비교.
        # 종가 확정 후(장 마감 시점) 판단·체결이므로 룩어헤드가 아니다.
        self._closes.append(bar.close)
        fast_ma = self._ma(self.fast)
        slow_ma = self._ma(self.slow)
        pf, ps = self._prev_fast, self._prev_slow

        if fast_ma is not None and slow_ma is not None and pf is not None and ps is not None:
            golden = pf <= ps and fast_ma > slow_ma
            dead = pf >= ps and fast_ma < slow_ma
            if golden and not position.is_open:
                signals.append(
                    Signal(bar.symbol, Side.BUY, bar.close, stop_price=slow_ma,
                           reason=f"골든크로스 {self.fast}/{self.slow}")
                )
            elif dead and position.is_open:
                signals.append(
                    Signal(bar.symbol, Side.SELL, bar.close,
                           reason=f"데드크로스 {self.fast}/{self.slow}")
                )

        self._prev_fast, self._prev_slow = fast_ma, slow_ma
        return signals
