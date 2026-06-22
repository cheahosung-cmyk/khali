"""로테이션 라이브 엔진 테스트 (네트워크 없이 가짜 클라이언트)."""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from khali.config import OrderMode, Settings
from khali.exchange.base import ExchangeClient
from khali.exchange.models import Balance, Candle, OrderResult, Side, Ticker


def _candles(prices):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [Candle(base + timedelta(days=i), p, p, p, p, 1.0) for i, p in enumerate(prices)]


class FakeClient(ExchangeClient):
    def __init__(self, series: dict, prices: dict):
        self.series = series        # 일봉 시퀀스
        self.prices = prices        # 현재가
        self.buys, self.sells = [], []

    def get_candles(self, market, unit=60, count=200):
        return _candles(self.series[market.split("-")[1]])

    def get_ticker(self, market):
        sym = market.split("-")[1]
        return Ticker(market, self.prices[sym], datetime.now(timezone.utc))

    def get_balances(self):
        return [Balance("KRW", 50000, 0, 0)]

    def execute_buy(self, market, krw_amount, ref_price):
        self.buys.append(market)
        return OrderResult("x", market, Side.BUY, ref_price, krw_amount / ref_price,
                           krw_amount, 0, datetime.now(timezone.utc))

    def execute_sell(self, market, volume, ref_price):
        self.sells.append(market)
        return OrderResult("x", market, Side.SELL, ref_price, volume,
                           volume * ref_price, 0, datetime.now(timezone.utc))


def _settings(db, **kw):
    return Settings(
        api_version=1, order_mode=OrderMode.PAPER, engine="rotation",
        base_capital_krw=50000, fee_rate=0.0004, slippage_pct=0.0,
        rotation_basket="AAA,BBB", rotation_regime_ma=20,
        rotation_rebalance_days=30, database_url=f"sqlite:///{db}", **kw,
    )


def _init(db):
    from khali.storage.db import init_db
    init_db(f"sqlite:///{db}")


def test_rotation_engine_enters_strongest_in_bull():
    from khali.engine.rotation_trader import RotationTrader
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "r.db"); _init(db)
        up = [100 + i * 2 for i in range(60)]      # AAA 강세
        flat = [100 + i * 0.1 for i in range(60)]  # BBB 약세
        btc_up = [100 + i for i in range(60)]      # BTC 강세(불레짐)
        client = FakeClient({"AAA": up, "BBB": flat, "BTC": btc_up},
                            {"AAA": 220, "BBB": 106, "BTC": 160})
        t = RotationTrader(_settings(db), client)
        t.step()
        assert t.held_symbol == "AAA"          # 상대강도 1위 진입
        assert t.regime == "bull"


def test_rotation_engine_goes_cash_in_bear():
    from khali.engine.rotation_trader import RotationTrader
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "r.db"); _init(db)
        coin = [100 + i for i in range(60)]
        btc_down = [300 - i * 2 for i in range(60)]   # BTC 약세(베어레짐)
        client = FakeClient({"AAA": coin, "BBB": coin, "BTC": btc_down},
                            {"AAA": 159, "BBB": 159, "BTC": 180})
        t = RotationTrader(_settings(db), client)
        t.step()
        assert t.held_symbol is None           # 베어 → 현금
        assert t.regime == "bear"


def test_kill_switch_liquidates_and_stops():
    from khali.engine.rotation_trader import RotationTrader
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "r.db"); _init(db)
        up = [100 + i for i in range(60)]
        btc_up = [100 + i for i in range(60)]
        client = FakeClient({"AAA": up, "BBB": up, "BTC": btc_up},
                            {"AAA": 159, "BBB": 159, "BTC": 159})
        t = RotationTrader(_settings(db, max_drawdown_stop_pct=0.1), client)
        # 보유 상태로 만들고 고점 설정
        t.step()
        t.peak_equity = 100000          # 인위적 고점 → 현재 평가가 고점대비 -50%
        t.step()
        assert t.killed is True
        assert t.held_symbol is None    # 청산됨
