"""변동성 돌파 전략 단위 테스트."""

from datetime import datetime, timedelta

from khali.models import Bar, Position, Side
from khali.strategy.volatility_breakout import VolatilityBreakout


def _bar(symbol, day, o, h, l, c):
    return Bar(symbol, datetime(2026, 1, 1) + timedelta(days=day), o, h, l, c, 1000)


def test_no_signal_without_prev_bar():
    strat = VolatilityBreakout(k=0.5, ma_window=1)
    signals = strat.on_bar(_bar("A", 0, 100, 110, 90, 105), Position("A"))
    assert signals == []


def test_breakout_generates_buy():
    strat = VolatilityBreakout(k=0.5, ma_window=1, atr_window=1)
    # 전일 봉: 고저폭 20
    strat.on_bar(_bar("A", 0, 100, 110, 90, 100), Position("A"))
    # 당일 시가 100 + 20*0.5 = 110 목표. 고가 120이 돌파.
    signals = strat.on_bar(_bar("A", 1, 100, 120, 95, 115), Position("A"))
    buys = [s for s in signals if s.side == Side.BUY]
    assert len(buys) == 1
    assert buys[0].price == 110


def test_no_breakout_when_high_below_target():
    strat = VolatilityBreakout(k=0.5, ma_window=1, atr_window=1)
    strat.on_bar(_bar("A", 0, 100, 110, 90, 100), Position("A"))
    # 목표 110, 고가 108 → 미돌파
    signals = strat.on_bar(_bar("A", 1, 100, 108, 95, 105), Position("A"))
    assert [s for s in signals if s.side == Side.BUY] == []


def test_trend_filter_blocks_below_ma():
    # 룩어헤드 제거 후: 필터는 '전일 종가'가 '전일까지 MA' 위인지로 판단.
    strat = VolatilityBreakout(k=0.5, ma_window=2, atr_window=1)
    strat.on_bar(_bar("A", 0, 200, 210, 190, 200), Position("A"))
    # 전일(day1) 종가 180. day2 시점 MA=(200+180)/2=190 > 180 → 약세 → 차단
    strat.on_bar(_bar("A", 1, 180, 185, 175, 180), Position("A"))
    # day2: 목표 180+range(10)*0.5=185, 고가 230으로 돌파하지만 추세필터가 막음
    signals = strat.on_bar(_bar("A", 2, 180, 230, 140, 200), Position("A"))
    assert [s for s in signals if s.side == Side.BUY] == []


def test_trend_filter_allows_above_ma():
    # 전일 종가가 MA 위면 돌파 진입 허용.
    strat = VolatilityBreakout(k=0.5, ma_window=2, atr_window=1)
    strat.on_bar(_bar("A", 0, 100, 110, 90, 100), Position("A"))
    # 전일(day1) 종가 120. day2 MA=(100+120)/2=110 < 120 → 강세
    strat.on_bar(_bar("A", 1, 110, 125, 105, 120), Position("A"))
    signals = strat.on_bar(_bar("A", 2, 120, 200, 115, 150), Position("A"))
    assert any(s.side == Side.BUY for s in signals)


def test_open_position_triggers_close():
    strat = VolatilityBreakout(k=0.5, ma_window=1, atr_window=1)
    strat.on_bar(_bar("A", 0, 100, 110, 90, 100), Position("A"))
    pos = Position("A", qty=10, avg_price=100)
    signals = strat.on_bar(_bar("A", 1, 100, 120, 95, 115), pos)
    sells = [s for s in signals if s.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].price == 115  # 종가 청산
