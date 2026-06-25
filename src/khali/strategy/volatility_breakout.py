"""변동성 돌파 전략 (Larry Williams) + 추세 필터 + ATR.

규칙(1번 채택 전략):
- 목표가 = 당일 시가 + (전일 고저폭 × k)
- 진입: 당일 고가가 목표가를 돌파하면 매수 (당일 시가 기준 추세장 추종)
- 추세 필터: 종가가 N일 이동평균 위일 때만 진입 (강세장 적합, 하락반전 회피)
- 청산: 당일 종가 청산 (오버나잇 갭 리스크 회피 — 초기 버전)
- ATR: 리스크 매니저가 포지션 사이징/손절에 사용하도록 함께 노출

현재 한국 시장(2026-06: 강추세 + 고변동성)에 맞춰 패널이 만장일치 채택.
"""

from __future__ import annotations

from collections import deque

from khali.models import Bar, Position, Side, Signal
from khali.strategy.base import Strategy


class VolatilityBreakout(Strategy):
    name = "volatility_breakout"

    def __init__(self, k: float = 0.5, ma_window: int = 5, atr_window: int = 14):
        if not 0 < k <= 1.0:
            raise ValueError("k는 (0, 1] 범위여야 합니다")
        self.k = k
        self.ma_window = ma_window
        self.atr_window = atr_window

        self._prev_bar: Bar | None = None
        self._closes: deque[float] = deque(maxlen=ma_window)
        self._true_ranges: deque[float] = deque(maxlen=atr_window)
        self._entered_today = False

    def warmup(self) -> int:
        return max(self.ma_window, self.atr_window) + 1

    @property
    def atr(self) -> float | None:
        if len(self._true_ranges) < self.atr_window:
            return None
        return sum(self._true_ranges) / len(self._true_ranges)

    def _moving_average(self) -> float | None:
        if len(self._closes) < self.ma_window:
            return None
        return sum(self._closes) / len(self._closes)

    def on_bar(self, bar: Bar, position: Position) -> list[Signal]:
        signals: list[Signal] = []
        prev = self._prev_bar

        # ATR용 True Range 갱신 (전일 종가 필요)
        if prev is not None:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev.close),
                abs(bar.low - prev.close),
            )
            self._true_ranges.append(tr)

        ma = self._moving_average()

        # --- 진입 판단: 전일 봉이 있어야 목표가 계산 가능 ---
        if prev is not None and not position.is_open and not self._entered_today:
            target = bar.open + prev.range * self.k
            trend_ok = ma is None or bar.close >= ma  # warmup 중엔 필터 통과 허용

            if bar.high >= target and trend_ok:
                atr = self.atr
                stop = bar.close - atr if atr else None
                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        side=Side.BUY,
                        price=target,
                        stop_price=stop,
                        reason=(
                            f"돌파 target={target:.1f} k={self.k} "
                            f"ma={ma if ma else 'NA'}"
                        ),
                    )
                )
                self._entered_today = True

        # --- 청산: 보유 중이면 당일 종가 청산 ---
        if position.is_open:
            signals.append(
                Signal(
                    symbol=bar.symbol,
                    side=Side.SELL,
                    price=bar.close,
                    reason="당일 종가 청산",
                )
            )

        # 다음 봉을 위한 상태 갱신
        self._closes.append(bar.close)
        self._prev_bar = bar
        self._entered_today = False  # 일봉 기준: 다음 봉은 새 날
        return signals
