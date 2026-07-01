"""추세 추종형 변동성 돌파 — 오버나잇 보유 + ATR 트레일링 스톱.

수익률 우선 원칙(3차 반복)에 따라, 강세장에서 오버나잇 상승분을 포기하던
종가청산형(VolatilityBreakout)을 대체하는 전략.

규칙:
- 진입: 당일 시가 + (전일 고저폭 × k) 돌파 + 전일 종가가 전일까지 MA 위
        (룩어헤드 없음). 갭상승 시 시가 체결.
- 보유: 청산 신호 전까지 **오버나잇 보유** (추세를 끝까지 탄다)
- 청산: 보유 중 고점(high) 갱신을 추적, 가격이 (최고가 − ATR×trail_mult)
        아래로 내려오면 트레일링 스톱 발동. 갭하락이면 시가 체결로 보수 모델링.
"""

from __future__ import annotations

from collections import deque

from khali.analysis.indicators import sma, true_range
from khali.models import Bar, Position, Side, Signal
from khali.strategy.base import Strategy


class TrendBreakout(Strategy):
    name = "trend_breakout"

    def __init__(
        self,
        k: float = 0.5,
        ma_window: int = 20,
        atr_window: int = 14,
        trail_mult: float = 2.5,
    ):
        if not 0 < k <= 1.0:
            raise ValueError("k는 (0, 1] 범위여야 합니다")
        if trail_mult <= 0:
            raise ValueError("trail_mult는 양수여야 합니다")
        self.k = k
        self.ma_window = ma_window
        self.atr_window = atr_window
        self.trail_mult = trail_mult

        self._prev_bar: Bar | None = None
        self._closes: deque[float] = deque(maxlen=ma_window)
        self._true_ranges: deque[float] = deque(maxlen=atr_window)
        self._trail_high: float | None = None  # 보유 중 최고가 추적

    def warmup(self) -> int:
        return max(self.ma_window, self.atr_window) + 1

    @property
    def atr(self) -> float | None:
        return sma(self._true_ranges, self.atr_window)

    def _moving_average(self) -> float | None:
        return sma(self._closes, self.ma_window)

    def on_bar(self, bar: Bar, position: Position) -> list[Signal]:
        signals: list[Signal] = []
        prev = self._prev_bar
        ma = self._moving_average()
        atr = self.atr

        if position.is_open:
            # 보유 중: 트레일링 스톱 관리. 보유 첫 봉이면 고점 초기화.
            if self._trail_high is None:
                self._trail_high = bar.high
            self._trail_high = max(self._trail_high, bar.high)
            if atr is not None:
                stop = self._trail_high - atr * self.trail_mult
                if bar.low <= stop:
                    # 갭하락으로 시가가 스톱 아래면 시가 체결(보수적)
                    fill = bar.open if bar.open < stop else stop
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            side=Side.SELL,
                            price=fill,
                            reason=f"트레일링 스톱 {stop:.1f} "
                            f"(고점 {self._trail_high:.1f}, ATR {atr:.1f})",
                        )
                    )
                    self._trail_high = None
        else:
            # 미보유: 진입 판단
            self._trail_high = None
            if prev is not None:
                target = bar.open + prev.range * self.k
                trend_ok = ma is None or prev.close >= ma
                if bar.high >= target and trend_ok:
                    fill = bar.open if bar.open > target else target
                    stop0 = fill - atr * self.trail_mult if atr else None
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            side=Side.BUY,
                            price=fill,
                            stop_price=stop0,
                            reason=f"돌파 진입 target={target:.1f} k={self.k}",
                        )
                    )
                    # 진입봉의 고가로 트레일 고점을 시드(다음 봉부터 누락 방지)
                    self._trail_high = bar.high

        # 상태 갱신 (의사결정 이후)
        if prev is not None:
            self._true_ranges.append(true_range(bar.high, bar.low, prev.close))
        self._closes.append(bar.close)
        self._prev_bar = bar
        return signals
