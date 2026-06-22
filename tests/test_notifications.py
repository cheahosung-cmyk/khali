"""알림 배선 테스트: 엔진이 매수/매도/킬스위치 시 notifier.send 호출."""

import os
import tempfile
from datetime import datetime, timedelta, timezone

from khali.config import OrderMode, Settings
from khali.exchange.base import ExchangeClient
from khali.exchange.models import Balance, Candle, OrderResult, Side, Ticker


class SpyNotifier:
    def __init__(self):
        self.messages = []

    @property
    def enabled(self):
        return True

    def send(self, text):
        self.messages.append(text)


def _candles(prices):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [Candle(base + timedelta(days=i), p, p, p, p, 1.0) for i, p in enumerate(prices)]


class FakeClient(ExchangeClient):
    def __init__(self, series, prices):
        self.series, self.prices = series, prices

    def get_candles(self, market, unit=60, count=200):
        return _candles(self.series[market.split("-")[1]])

    def get_ticker(self, market):
        return Ticker(market, self.prices[market.split("-")[1]], datetime.now(timezone.utc))

    def get_balances(self):
        return [Balance("KRW", 50000, 0, 0)]

    def execute_buy(self, market, krw_amount, ref_price):
        return OrderResult("x", market, Side.BUY, ref_price, krw_amount / ref_price,
                           krw_amount, 0, datetime.now(timezone.utc))

    def execute_sell(self, market, volume, ref_price):
        return OrderResult("x", market, Side.SELL, ref_price, volume,
                           volume * ref_price, 0, datetime.now(timezone.utc))


def test_rotation_notifies_on_entry():
    from khali.engine.rotation_trader import RotationTrader
    from khali.storage.db import init_db
    with tempfile.TemporaryDirectory() as d:
        init_db(f"sqlite:///{os.path.join(d, 'n.db')}")
        up = [100 + i * 2 for i in range(60)]
        flat = [100 + i * 0.1 for i in range(60)]
        btc = [100 + i for i in range(60)]
        client = FakeClient({"AAA": up, "BBB": flat, "BTC": btc},
                            {"AAA": 220, "BBB": 106, "BTC": 160})
        s = Settings(api_version=1, order_mode=OrderMode.PAPER, engine="rotation",
                     base_capital_krw=50000, rotation_basket="AAA,BBB",
                     rotation_regime_ma=20, rotation_lookback=30,
                     database_url=f"sqlite:///{os.path.join(d,'n.db')}")
        t = RotationTrader(s, client)
        spy = SpyNotifier(); t.notifier = spy
        t.step()
        assert any("매수" in m for m in spy.messages)


def test_single_engine_notifies_on_buy(candle_factory):
    from khali.engine.trader import Trader
    from khali.storage.db import init_db
    with tempfile.TemporaryDirectory() as d:
        init_db(f"sqlite:///{os.path.join(d, 'n2.db')}")
        prices = [100] * 35 + [130]   # 골든크로스 매수 유발 (종가 기반)
        client = FakeClient({"XRP": prices}, {"XRP": 130})
        s = Settings(api_version=1, order_mode=OrderMode.PAPER, engine="single",
                     market="KRW-XRP", strategy="ma_crossover",
                     base_capital_krw=50000, database_url=f"sqlite:///{os.path.join(d,'n2.db')}")
        t = Trader(s, client)
        spy = SpyNotifier(); t.notifier = spy
        t.step()
        assert any("매수" in m for m in spy.messages)
