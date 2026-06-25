"""리스크 레이어 — 모든 주문의 게이트키퍼.

전략이 아무리 좋아도 단 한 번의 버그/폭락에 계좌가 0이 되지 않도록 막는
가장 중요한 컴포넌트. 신호(Signal)를 받아 실제 주문 수량으로 변환하거나,
한도 위반 시 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from khali.models import Account, Side, Signal


@dataclass
class RiskConfig:
    # 1회 진입 시 감수할 자본 비율 (예: 1% 룰)
    risk_per_trade: float = 0.01
    # 단일 종목 최대 비중 (쏠림 방지 — 현 시장 핵심 리스크)
    max_position_pct: float = 0.20
    # 일일 최대 손실 비율. 초과 시 kill-switch 발동
    daily_max_loss_pct: float = 0.03
    # 동시 보유 가능한 최대 종목 수
    max_open_positions: int = 5
    # 기본 손절폭 비율 (전략이 stop_price를 안 줄 때 fallback)
    default_stop_pct: float = 0.05


class RiskManager:
    def __init__(self, config: RiskConfig, start_equity: float):
        self.config = config
        self.start_of_day_equity = start_equity
        self._halted = False

    @property
    def halted(self) -> bool:
        return self._halted

    def start_new_day(self, equity: float) -> None:
        """매 거래일 시작 시 기준 자본을 리셋하고 정지를 해제한다."""
        self.start_of_day_equity = equity
        self._halted = False

    def check_daily_loss(self, equity: float) -> bool:
        """일일 손실 한도 초과 여부. 초과 시 kill-switch 발동."""
        loss = (self.start_of_day_equity - equity) / self.start_of_day_equity
        if loss >= self.config.daily_max_loss_pct:
            self._halted = True
        return self._halted

    def size_order(
        self, signal: Signal, account: Account, price: float
    ) -> int:
        """신호를 실제 주문 수량(주)으로 변환. 거부 시 0 반환.

        매도(청산)는 보유 수량 전량을 반환한다.
        매수는 (1) kill-switch (2) 종목수 한도 (3) ATR/손절 기반 사이징
        (4) 단일종목 비중 상한 (5) 현금 한도를 차례로 적용한다.
        """
        pos = account.positions.get(signal.symbol)

        # --- 청산 ---
        if signal.side == Side.SELL:
            return pos.qty if pos and pos.qty > 0 else 0

        # --- 매수 게이트 ---
        if self._halted:
            return 0

        open_count = sum(1 for p in account.positions.values() if p.is_open)
        if pos is None or not pos.is_open:
            if open_count >= self.config.max_open_positions:
                return 0

        equity = account.equity({signal.symbol: price})

        # 손절폭: 전략 제안 우선, 없으면 기본 비율
        if signal.stop_price is not None and signal.stop_price < price:
            stop_dist = price - signal.stop_price
        else:
            stop_dist = price * self.config.default_stop_pct
        if stop_dist <= 0:
            return 0

        # 1% 룰: 감수 자본 / 1주당 손실폭 = 수량
        risk_capital = equity * self.config.risk_per_trade
        qty_by_risk = int(risk_capital // stop_dist)

        # 단일 종목 비중 상한
        max_notional = equity * self.config.max_position_pct
        qty_by_concentration = int(max_notional // price)

        # 현금 한도
        qty_by_cash = int(account.cash // price)

        qty = min(qty_by_risk, qty_by_concentration, qty_by_cash)
        return max(qty, 0)
