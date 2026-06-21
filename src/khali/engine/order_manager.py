"""주문 실행 추상화: backtest / paper / live 모드 통일.

- backtest, paper: 주어진 가격에 즉시 체결 + 수수료 차감으로 시뮬레이션
- live: 빗썸 시장가 주문 후 체결 결과 반영

세 모드 모두 동일한 OrderResult 를 반환하므로 상위 엔진은 모드를 신경
쓰지 않는다. 실제 돈이 나가는 곳은 live 분기 단 한 곳뿐이다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ..config import OrderMode
from ..exchange.base import ExchangeClient
from ..exchange.models import OrderResult, Side
from .portfolio import Portfolio

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(
        self,
        mode: OrderMode,
        fee_rate: float,
        portfolio: Portfolio,
        client: ExchangeClient | None = None,
        slippage_pct: float = 0.0,
    ):
        self.mode = mode
        self.fee_rate = fee_rate
        self.portfolio = portfolio
        self.client = client
        self.slippage_pct = slippage_pct

    @property
    def simulated(self) -> bool:
        return self.mode in (OrderMode.BACKTEST, OrderMode.PAPER)

    # ────────────────────── 매수 ──────────────────────
    def buy(self, market: str, krw_amount: float, price: float) -> OrderResult:
        if self.simulated:
            fill = price * (1 + self.slippage_pct)  # 매수는 불리하게 +슬리피지
            fee = krw_amount * self.fee_rate
            volume = (krw_amount - fee) / fill
            self.portfolio.apply_buy(fill, volume, krw_amount)
            return OrderResult(
                uuid=str(uuid.uuid4()),
                market=market,
                side=Side.BUY,
                price=fill,
                volume=volume,
                paid_krw=krw_amount,
                fee=fee,
                created_at=datetime.now(timezone.utc),
                simulated=True,
            )
        return self._live_buy(market, krw_amount, price)

    # ────────────────────── 매도 ──────────────────────
    def sell(self, market: str, volume: float, price: float) -> OrderResult:
        if self.simulated:
            fill = price * (1 - self.slippage_pct)  # 매도는 불리하게 -슬리피지
            gross = volume * fill
            fee = gross * self.fee_rate
            received = gross - fee
            self.portfolio.apply_sell(fill, volume, received)
            return OrderResult(
                uuid=str(uuid.uuid4()),
                market=market,
                side=Side.SELL,
                price=fill,
                volume=volume,
                paid_krw=received,
                fee=fee,
                created_at=datetime.now(timezone.utc),
                simulated=True,
            )
        return self._live_sell(market, volume, price)

    # ────────────────────── live 분기 ──────────────────────
    def _live_buy(self, market: str, krw_amount: float, price: float) -> OrderResult:
        if not self.client:
            raise RuntimeError("live 모드인데 거래소 클라이언트가 없습니다.")
        result = self.client.execute_buy(market, krw_amount, price)
        if result.volume:
            self.portfolio.apply_buy(result.price, result.volume, result.paid_krw)
        return result

    def _live_sell(self, market: str, volume: float, price: float) -> OrderResult:
        if not self.client:
            raise RuntimeError("live 모드인데 거래소 클라이언트가 없습니다.")
        result = self.client.execute_sell(market, volume, price)
        if result.volume:
            self.portfolio.apply_sell(result.price, result.volume, result.paid_krw)
        return result
