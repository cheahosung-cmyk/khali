"""변동성 돌파 전략 (Larry Williams) + 추세 필터 + ATR.

규칙(1번 채택 전략):
- 목표가 = 당일 시가 + (전일 고저폭 × k)
- 진입: 당일 고가가 목표가를 돌파하면 목표가에 매수 (장중 돌파 시점)
- 추세 필터: **전일 종가**가 **전일까지의** N일 이동평균 위일 때만 진입
  → 진입 시점에 이미 확정된 정보만 사용하므로 룩어헤드 바이어스 없음
- 청산: 당일 종가 청산 (오버나잇 갭 리스크 회피 — 초기 버전)
- ATR: 리스크 매니저가 포지션 사이징/손절에 사용하도록 함께 노출

전문가 패널 수정 반영:
- 진입/청산 체결가 분리 (엔진이 처리), 룩어헤드 제거, 상태 단순화.
"""

from __future__ import annotations

from collections import deque

from khali.analysis.indicators import sma, true_range
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
        # 완료된(과거) 종가만 보관 — 오늘 종가는 의사결정 후에 추가한다.
        self._closes: deque[float] = deque(maxlen=ma_window)
        self._true_ranges: deque[float] = deque(maxlen=atr_window)

    def warmup(self) -> int:
        return max(self.ma_window, self.atr_window) + 1

    @property
    def atr(self) -> float | None:
        return sma(self._true_ranges, self.atr_window)

    def _moving_average(self) -> float | None:
        """전일까지의 완료된 종가 기준 이동평균 (룩어헤드 없음)."""
        return sma(self._closes, self.ma_window)

    def on_bar(self, bar: Bar, position: Position) -> list[Signal]:
        signals: list[Signal] = []
        prev = self._prev_bar
        ma = self._moving_average()  # 전일까지 종가 기준

        # --- 진입: 전일 봉 필요. 진입가/추세필터 모두 확정 정보만 사용 ---
        if prev is not None and not position.is_open:
            target = bar.open + prev.range * self.k
            # 추세 필터: 전일 종가가 전일까지 MA 위 (장중에 이미 확정된 값)
            trend_ok = ma is None or prev.close >= ma
            if bar.high >= target and trend_ok:
                atr = self.atr
                # 갭상승으로 시가가 목표가 위면 시가 체결 (전략이 갭 모델링)
                fill = bar.open if bar.open > target else target
                stop = fill - atr if atr else None
                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        side=Side.BUY,
                        price=fill,
                        stop_price=stop,
                        reason=f"돌파 target={target:.1f} k={self.k} "
                        f"ma={ma:.1f}" if ma else f"돌파 target={target:.1f}",
                    )
                )

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

        # --- 다음 봉을 위한 상태 갱신 (의사결정 이후) ---
        if prev is not None:
            self._true_ranges.append(true_range(bar.high, bar.low, prev.close))
        self._closes.append(bar.close)
        self._prev_bar = bar
        return signals
