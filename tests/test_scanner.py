"""상대강도 스캐너 오프라인 테스트 (가짜 클라이언트)."""

from datetime import datetime, timedelta, timezone

from khali.analysis.scanner import market_regime, scan, score_market
from khali.exchange.base import ExchangeClient
from khali.exchange.models import Candle, Ticker


class FakeMarketClient(ExchangeClient):
    """심볼별로 미리 정해진 종가 시퀀스를 돌려주는 클라이언트."""

    def __init__(self, series: dict[str, list[float]]):
        self.series = series

    def get_candles(self, market, unit=60, count=200):
        sym = market.split("-")[1]
        prices = self.series[sym]
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return [
            Candle(base + timedelta(days=i), p, p, p, p, 1.0)
            for i, p in enumerate(prices)
        ]

    def get_ticker(self, market):
        return Ticker(market, 1.0, datetime.now(timezone.utc))

    def get_balances(self):
        return []

    def execute_buy(self, market, krw_amount, ref_price):
        raise NotImplementedError

    def execute_sell(self, market, volume, ref_price):
        raise NotImplementedError


def test_scan_ranks_strongest_first():
    up = [100 + i for i in range(250)]        # 꾸준한 상승
    flat = [100] * 250                         # 횡보
    down = [350 - i for i in range(250)]       # 하락
    client = FakeMarketClient({"UP": up, "FLAT": flat, "DOWN": down})
    rows = scan(client, ["DOWN", "FLAT", "UP"])
    assert [r.symbol for r in rows] == ["UP", "FLAT", "DOWN"]  # 강→약 정렬
    assert rows[0].trend == "bull"
    assert rows[-1].trend == "bear"


def test_market_regime_uses_btc():
    up = [100 + i for i in range(250)]
    down = [350 - i for i in range(250)]
    assert market_regime(FakeMarketClient({"BTC": up})) == "bull"
    assert market_regime(FakeMarketClient({"BTC": down})) == "bear"


def test_score_market_fields():
    up = [100 + i for i in range(250)]
    s = score_market(FakeMarketClient({"XRP": up}), "XRP")
    assert s is not None
    assert s.symbol == "XRP"
    assert s.return_30d_pct > 0
    assert s.trend == "bull"
