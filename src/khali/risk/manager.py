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
    # 현금 한도 계산 시 수수료/슬리피지 여유분 (전량 거부 방지)
    cash_buffer: float = 0.005


class RiskManager:
    def __init__(self, config: RiskConfig, start_equity: float):
        self.config = config
        # 기준 자본 = 직전 거래일 마지막 평가자본(전일 종가 기준). 첫날은 시작자본.
        self._baseline_equity = start_equity
        self._last_equity = start_equity
        self._day = None
        self._halted = False

    @property
    def halted(self) -> bool:
        return self._halted

    def observe(self, equity: float, day) -> bool:
        """매 봉 호출. 새 거래일이면 전일 마지막 자본을 기준선으로 승격하고
        kill-switch를 해제한다. 그 뒤 현재 자본이 기준선 대비 한도를 넘으면 정지.

        일봉에선 '전일 종가 자본 대비 당일 자본' 비교가 되어 한도가 실제로
        작동한다(이전엔 매 봉 기준을 현재값으로 리셋해 영구 무력화됐음).
        장중(하루 여러 봉)에선 기준선이 그날 동안 고정돼 누적 낙폭을 잡는다.
        """
        if day != self._day:
            if self._day is not None:
                self._baseline_equity = self._last_equity  # 전일 마지막 자본
            self._day = day
            self._halted = False
        self._last_equity = equity
        if self._baseline_equity > 0:
            loss = (self._baseline_equity - equity) / self._baseline_equity
            if loss >= self.config.daily_max_loss_pct:
                self._halted = True
        return self._halted

    def size_order(
        self, signal: Signal, account: Account, price: float,
        marks: dict[str, float] | None = None,
    ) -> int:
        """신호를 실제 주문 수량(주)으로 변환. 거부 시 0 반환.

        매도(청산)는 보유 수량 전량을 반환한다.
        매수는 (1) kill-switch (2) 종목수 한도 (3) ATR/손절 기반 사이징
        (4) 단일종목 비중 상한 (5) 현금 한도를 차례로 적용한다.

        marks: 전체 종목의 현재가. 자본(equity) 평가에 사용한다. 없으면 신호
        종목만 현재가로 평가(타 보유는 원가) — 단일종목 백테스트용 폴백.
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

        equity = account.equity(marks if marks else {signal.symbol: price})

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

        # 현금 한도 (수수료/슬리피지 여유분 반영 → 전량 거부 방지)
        qty_by_cash = int(account.cash // (price * (1 + self.config.cash_buffer)))

        qty = min(qty_by_risk, qty_by_concentration, qty_by_cash)
        return max(qty, 0)
