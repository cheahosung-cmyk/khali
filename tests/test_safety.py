"""안전성·정합성 검증 테스트.

핵심 불변식을 코드로 증명한다:
  - paper/backtest 모드는 거래소에 절대 주문을 내지 않는다 (실거래 차단)
  - live 모드만 클라이언트 주문 메서드를 호출한다
  - 백테스트에서 자금이 보존된다 (음수 현금/포지션 없음)
"""

from datetime import datetime, timezone

import pytest

from khali.config import OrderMode, Settings
from khali.engine.order_manager import OrderManager
from khali.engine.portfolio import Portfolio
from khali.exchange.base import ExchangeClient
from khali.exchange.models import Balance, Candle, OrderResult, Side, Ticker


class SpyClient(ExchangeClient):
    """주문 호출 여부를 기록하는 가짜 클라이언트."""

    def __init__(self):
        self.buy_calls = 0
        self.sell_calls = 0

    def get_candles(self, market, unit=60, count=200):
        return []

    def get_ticker(self, market):
        return Ticker(market=market, trade_price=1000.0, timestamp=datetime.now(timezone.utc))

    def get_balances(self):
        return [Balance("KRW", 50000, 0, 0)]

    def execute_buy(self, market, krw_amount, ref_price):
        self.buy_calls += 1
        return OrderResult("x", market, Side.BUY, ref_price,
                           krw_amount / ref_price, krw_amount, 0,
                           datetime.now(timezone.utc), simulated=False)

    def execute_sell(self, market, volume, ref_price):
        self.sell_calls += 1
        return OrderResult("x", market, Side.SELL, ref_price, volume,
                           volume * ref_price, 0, datetime.now(timezone.utc),
                           simulated=False)


@pytest.mark.parametrize("mode", [OrderMode.PAPER, OrderMode.BACKTEST])
def test_simulated_modes_never_touch_client(mode):
    spy = SpyClient()
    pf = Portfolio(cash_krw=50000)
    om = OrderManager(mode, fee_rate=0.0004, portfolio=pf, client=spy)
    om.buy("KRW-XRP", 10000, 1000)
    om.sell("KRW-XRP", 5.0, 1100)
    assert spy.buy_calls == 0      # 시뮬레이션은 거래소 호출 0
    assert spy.sell_calls == 0


def test_live_mode_calls_client():
    spy = SpyClient()
    pf = Portfolio(cash_krw=50000)
    om = OrderManager(OrderMode.LIVE, fee_rate=0.0004, portfolio=pf, client=spy)
    om.buy("KRW-XRP", 10000, 1000)
    om.sell("KRW-XRP", 5.0, 1100)
    assert spy.buy_calls == 1
    assert spy.sell_calls == 1


def test_backtest_no_negative_cash_or_position(settings, candle_factory):
    from khali.backtest.backtester import Backtester

    prices = []
    for _ in range(60):
        prices += [100, 105, 110, 102, 96, 108]
    candles = candle_factory(prices)
    # 전량 진입(position_size=1.0)에서도 음수 자산이 없어야 함
    settings.position_size_pct = 1.0
    bt = Backtester(settings)
    r = bt.run(candles, "volatility_breakout")
    assert r.final_value >= 0
    for v in r.equity_curve:
        assert v >= 0


def test_min_order_blocks_dust_capital(settings):
    from khali.risk.risk_manager import DayState, DecisionType, PositionState, RiskManager
    from khali.strategies.base import Action, Signal

    settings.min_order_krw = 5000
    settings.position_size_pct = 1.0
    rm = RiskManager(settings)
    d = rm.evaluate(
        Signal(Action.BUY), PositionState(has_position=False),
        current_price=1000, day=DayState(capital=3000),  # 3000 < 5000
    )
    assert d.type == DecisionType.HOLD
