"""포트폴리오 상태 추적 (현금/포지션/실현손익).

paper·backtest 모드에서는 이 객체가 가상 잔고의 단일 진실원천이다.
live 모드에서는 sync_from_balances() 로 거래소 실제 잔고와 맞춘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..risk.risk_manager import PositionState


@dataclass
class Portfolio:
    cash_krw: float
    coin_volume: float = 0.0
    entry_price: float = 0.0
    high_price: float = 0.0           # 진입 후 최고가 (트레일링)
    realized_pnl_total: float = 0.0
    consecutive_losses: int = 0
    _trades: list = field(default_factory=list)

    @property
    def has_position(self) -> bool:
        return self.coin_volume > 1e-12

    def mark_price(self, price: float) -> None:
        """최신 시세 반영 - 트레일링용 고점 갱신."""
        if self.has_position and price > self.high_price:
            self.high_price = price

    def position_value(self, price: float) -> float:
        return self.coin_volume * price

    def total_value(self, price: float) -> float:
        return self.cash_krw + self.position_value(price)

    def position_state(self) -> PositionState:
        return PositionState(
            has_position=self.has_position,
            entry_price=self.entry_price,
            volume=self.coin_volume,
            high_price=self.high_price,
        )

    # ────────────────────── 체결 반영 ──────────────────────
    def apply_buy(self, price: float, volume: float, krw_spent: float) -> None:
        """매수 체결 반영. krw_spent 는 수수료 포함 총지출."""
        self.cash_krw -= krw_spent
        # 평균 진입가 갱신
        prev_cost = self.entry_price * self.coin_volume
        self.coin_volume += volume
        self.entry_price = (
            (prev_cost + price * volume) / self.coin_volume
            if self.coin_volume
            else price
        )
        self.high_price = max(self.high_price, price)

    def apply_sell(
        self, price: float, volume: float, krw_received: float
    ) -> float:
        """매도 체결 반영. 실현손익(KRW) 반환."""
        cost_basis = self.entry_price * volume
        realized = krw_received - cost_basis
        self.cash_krw += krw_received
        self.coin_volume -= volume
        self.realized_pnl_total += realized

        if realized < 0:
            self.consecutive_losses += 1
        elif realized > 0:
            self.consecutive_losses = 0

        if self.coin_volume <= 1e-12:
            self.coin_volume = 0.0
            self.entry_price = 0.0
            self.high_price = 0.0
        return realized

    def sync_from_balances(self, balances, market: str) -> None:
        """live 모드: 거래소 실제 잔고로 포지션 동기화."""
        base = market.split("-")[0]   # KRW
        coin = market.split("-")[1]   # XRP
        for b in balances:
            if b.currency == base:
                self.cash_krw = b.total
            elif b.currency == coin:
                self.coin_volume = b.total
                if b.avg_buy_price:
                    self.entry_price = b.avg_buy_price
                    self.high_price = max(self.high_price, b.avg_buy_price)
