"""리스크 매니저: 전략 신호를 받아 최종 매매 결정을 내린다.

수익률을 지키는 핵심 레이어. 전략이 BUY 를 외쳐도 일일 손실 한도 초과,
연속 손실 쿨다운, 최소 주문금액 미달이면 거부한다. 보유 중에는 전략
신호와 무관하게 손절/익절/트레일링 스탑을 강제한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..strategies.base import Action, Signal


class DecisionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class RiskDecision:
    type: DecisionType
    reason: str
    krw_amount: float = 0.0   # 매수 시 투입 금액
    volume: float = 0.0       # 매도 시 청산 수량


@dataclass
class PositionState:
    has_position: bool = False
    entry_price: float = 0.0
    volume: float = 0.0
    high_price: float = 0.0   # 진입 후 최고가 (트레일링용)


@dataclass
class DayState:
    realized_pnl_today: float = 0.0   # 당일 실현손익 (KRW)
    consecutive_losses: int = 0
    capital: float = 0.0              # 현재 운용 자본 (KRW)


class RiskManager:
    def __init__(self, settings):
        self.s = settings

    def evaluate(
        self,
        signal: Signal,
        pos: PositionState,
        current_price: float,
        day: DayState,
    ) -> RiskDecision:
        s = self.s

        # ── 보유 중: 청산 조건을 가장 먼저 강제 검사 ──
        if pos.has_position and pos.entry_price > 0:
            change = (current_price - pos.entry_price) / pos.entry_price

            if change <= -s.stop_loss_pct:
                return self._sell(pos, f"손절 {change:.2%}")
            if change >= s.take_profit_pct:
                return self._sell(pos, f"익절 {change:.2%}")

            # 트레일링 스탑: 진입 후 고점 대비 하락폭
            peak = max(pos.high_price, current_price)
            if peak > 0:
                drop = (current_price - peak) / peak
                if drop <= -s.trailing_stop_pct and current_price > pos.entry_price:
                    return self._sell(pos, f"트레일링 스탑 (고점대비 {drop:.2%})")

            if signal.action == Action.SELL:
                return self._sell(pos, f"전략 매도: {signal.reason}")

            return RiskDecision(DecisionType.HOLD, "보유 유지")

        # ── 미보유: 매수 가능 여부 검사 ──
        if signal.action == Action.BUY:
            blocked = self._buy_blocked(day)
            if blocked:
                return RiskDecision(DecisionType.HOLD, blocked)

            weight = signal.target_weight or s.position_size_pct
            krw = day.capital * weight
            if krw < s.min_order_krw:
                return RiskDecision(
                    DecisionType.HOLD,
                    f"주문금액 {krw:.0f}원 < 최소 {s.min_order_krw:.0f}원",
                )
            return RiskDecision(
                DecisionType.BUY,
                f"매수: {signal.reason}",
                krw_amount=round(krw),
            )

        return RiskDecision(DecisionType.HOLD, signal.reason or "대기")

    # ────────────────────── 내부 헬퍼 ──────────────────────
    def _buy_blocked(self, day: DayState) -> str | None:
        s = self.s
        loss_limit = -abs(s.daily_loss_limit_pct) * s.base_capital_krw
        if day.realized_pnl_today <= loss_limit:
            return (
                f"일일 손실 한도 도달 ({day.realized_pnl_today:.0f}원) - 당일 매매 중단"
            )
        if day.consecutive_losses >= s.max_consecutive_losses:
            return f"연속 손실 {day.consecutive_losses}회 - 쿨다운"
        return None

    @staticmethod
    def _sell(pos: PositionState, reason: str) -> RiskDecision:
        return RiskDecision(DecisionType.SELL, reason, volume=pos.volume)
