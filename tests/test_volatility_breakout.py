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
    strat = VolatilityBreakout(k=0.5, ma_window=2, atr_window=1)
    strat.on_bar(_bar("A", 0, 200, 210, 190, 200), Position("A"))
    strat.on_bar(_bar("A", 1, 200, 210, 190, 200), Position("A"))
    # MA=200. 당일 종가 150 < MA → 돌파해도 진입 차단
    signals = strat.on_bar(_bar("A", 2, 200, 230, 140, 150), Position("A"))
    assert [s for s in signals if s.side == Side.BUY] == []


def test_open_position_triggers_close():
    strat = VolatilityBreakout(k=0.5, ma_window=1, atr_window=1)
    strat.on_bar(_bar("A", 0, 100, 110, 90, 100), Position("A"))
    pos = Position("A", qty=10, avg_price=100)
    signals = strat.on_bar(_bar("A", 1, 100, 120, 95, 115), pos)
    sells = [s for s in signals if s.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].price == 115  # 종가 청산
