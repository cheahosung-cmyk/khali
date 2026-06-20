"""주문 실행 추상화: backtest / paper / live 모드 통일.

- backtest, paper: 주어진 가격에 즉시 체결 + 수수료 차감으로 시뮬레이션
- live: 빗썸 시장가 주문 후 체결 결과 반영

세 모드 모두 동일한 OrderResult 를 반환하므로 상위 엔진은 모드를 신경
쓰지 않는다. 실제 돈이 나가는 곳은 live 분기 단 한 곳뿐이다.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from ..config import OrderMode
from ..exchange.bithumb_client import BithumbClient
from ..exchange.models import OrderResult, Side
from .portfolio import Portfolio

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(
        self,
        mode: OrderMode,
        fee_rate: float,
        portfolio: Portfolio,
        client: BithumbClient | None = None,
    ):
        self.mode = mode
        self.fee_rate = fee_rate
        self.portfolio = portfolio
        self.client = client

    @property
    def simulated(self) -> bool:
        return self.mode in (OrderMode.BACKTEST, OrderMode.PAPER)

    # ────────────────────── 매수 ──────────────────────
    def buy(self, market: str, krw_amount: float, price: float) -> OrderResult:
        if self.simulated:
            fee = krw_amount * self.fee_rate
            volume = (krw_amount - fee) / price
            self.portfolio.apply_buy(price, volume, krw_amount)
            return OrderResult(
                uuid=str(uuid.uuid4()),
                market=market,
                side=Side.BUY,
                price=price,
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
            gross = volume * price
            fee = gross * self.fee_rate
            received = gross - fee
            self.portfolio.apply_sell(price, volume, received)
            return OrderResult(
                uuid=str(uuid.uuid4()),
                market=market,
                side=Side.SELL,
                price=price,
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
        resp = self.client.buy_market(market, krw_amount)
        filled = self._poll_fill(resp.get("uuid"))
        volume = float(filled.get("executed_volume") or 0)
        paid = float(filled.get("price") or krw_amount)
        fee = float(filled.get("paid_fee") or 0)
        avg_price = (paid / volume) if volume else price
        return OrderResult(
            uuid=resp.get("uuid", ""),
            market=market,
            side=Side.BUY,
            price=avg_price,
            volume=volume,
            paid_krw=paid,
            fee=fee,
            created_at=datetime.now(timezone.utc),
            simulated=False,
        )

    def _live_sell(self, market: str, volume: float, price: float) -> OrderResult:
        if not self.client:
            raise RuntimeError("live 모드인데 거래소 클라이언트가 없습니다.")
        resp = self.client.sell_market(market, volume)
        filled = self._poll_fill(resp.get("uuid"))
        exec_vol = float(filled.get("executed_volume") or volume)
        funds = float(filled.get("price") or 0) or exec_vol * price
        fee = float(filled.get("paid_fee") or 0)
        received = funds - fee
        avg_price = (funds / exec_vol) if exec_vol else price
        return OrderResult(
            uuid=resp.get("uuid", ""),
            market=market,
            side=Side.SELL,
            price=avg_price,
            volume=exec_vol,
            paid_krw=received,
            fee=fee,
            created_at=datetime.now(timezone.utc),
            simulated=False,
        )

    def _poll_fill(self, order_uuid: str | None, retries: int = 5) -> dict:
        """체결 완료까지 잠깐 폴링 (시장가는 보통 즉시 체결)."""
        if not order_uuid or not self.client:
            return {}
        last: dict = {}
        for _ in range(retries):
            last = self.client.get_order(order_uuid)
            if last.get("state") in ("done", "cancel"):
                return last
            time.sleep(0.3)
        return last
