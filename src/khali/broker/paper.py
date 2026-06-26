"""페이퍼(모의) 브로커 — 가상 현금으로 즉시 체결. 백테스트/페이퍼 공용.

수수료·슬리피지를 반영해 실거래에 가깝게 만든다. 한국 주식 기준
거래수수료+세금을 대략 반영(매도 시 거래세).
"""

from __future__ import annotations

from khali.broker.base import Broker
from khali.models import Account, Order, OrderStatus, Position, Side


class PaperBroker(Broker):
    def __init__(
        self,
        starting_cash: float,
        fee_rate: float = 0.00015,  # 위탁수수료(편도) 가정
        tax_rate: float = 0.0018,   # 매도 시 거래세(증권거래세+농특세 근사)
        slippage: float = 0.001,    # 체결 슬리피지
    ):
        self.account = Account(cash=starting_cash)
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.slippage = slippage
        self._marks: dict[str, float] = {}

    def set_mark(self, symbol: str, price: float) -> None:
        """백테스트 엔진이 현재 봉 가격을 주입한다."""
        self._marks[symbol] = price

    def last_price(self, symbol: str) -> float:
        return self._marks.get(symbol, 0.0)

    def get_account(self) -> Account:
        return self.account

    def submit(self, order: Order, ref_price: float | None = None) -> Order:
        # 체결 기준가: 명시되면 그 값을, 아니면 현재 평가 마크를 사용
        ref = ref_price if ref_price is not None else self._marks.get(order.symbol)
        if ref is None or order.qty <= 0:
            order.status = OrderStatus.REJECTED
            return order

        # 슬리피지: 매수는 불리하게 +, 매도는 -
        if order.side == Side.BUY:
            fill = ref * (1 + self.slippage)
            cost = fill * order.qty
            fee = cost * self.fee_rate
            total = cost + fee
            if total > self.account.cash:
                order.status = OrderStatus.REJECTED
                return order
            self.account.cash -= total
            pos = self.account.positions.get(order.symbol) or Position(order.symbol)
            new_qty = pos.qty + order.qty
            pos.avg_price = (pos.avg_price * pos.qty + cost) / new_qty
            pos.qty = new_qty
            self.account.positions[order.symbol] = pos
        else:  # SELL
            pos = self.account.positions.get(order.symbol)
            if not pos or pos.qty < order.qty:
                order.status = OrderStatus.REJECTED
                return order
            fill = ref * (1 - self.slippage)
            proceeds = fill * order.qty
            fee = proceeds * self.fee_rate
            tax = proceeds * self.tax_rate
            self.account.cash += proceeds - fee - tax
            pos.qty -= order.qty
            if pos.qty == 0:
                pos.avg_price = 0.0

        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.filled_price = fill
        return order
