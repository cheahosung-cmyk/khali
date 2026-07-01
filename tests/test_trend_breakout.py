"""TrendBreakout(오버나잇 보유 + 트레일링 스톱) 단위 테스트."""

from datetime import datetime, timedelta

from khali.models import Bar, Position, Side
from khali.strategy.trend_breakout import TrendBreakout


def _bar(day, o, h, l, c):
    return Bar("A", datetime(2026, 1, 1) + timedelta(days=day), o, h, l, c, 1000)


def test_breakout_entry_when_above_ma():
    strat = TrendBreakout(k=0.5, ma_window=1, atr_window=1, trail_mult=2.0)
    strat.on_bar(_bar(0, 100, 110, 90, 105), Position("A"))
    # target = 105 + range(20)*0.5 = 115, 고가 130 돌파, 전일종가 105>=MA(105)
    signals = strat.on_bar(_bar(1, 105, 130, 100, 125), Position("A"))
    buys = [s for s in signals if s.side == Side.BUY]
    assert len(buys) == 1
    assert buys[0].price == 115  # 시가<목표 → 목표가 체결


def test_holds_overnight_no_exit_in_uptrend():
    strat = TrendBreakout(k=0.5, ma_window=1, atr_window=1, trail_mult=2.0)
    strat.on_bar(_bar(0, 100, 110, 90, 105), Position("A"))
    strat.on_bar(_bar(1, 105, 130, 100, 125), Position("A"))
    # 보유 중 상승 지속 → 트레일링 스톱 미발동 (매도 신호 없음 = 오버나잇 보유)
    pos = Position("A", qty=10, avg_price=115)
    signals = strat.on_bar(_bar(2, 126, 140, 124, 138), pos)
    assert [s for s in signals if s.side == Side.SELL] == []


def test_trailing_stop_triggers_on_pullback():
    # ATR을 안정적으로 만들기 위해 일 변동폭을 10으로 일정하게 둔다.
    strat = TrendBreakout(k=0.5, ma_window=1, atr_window=1, trail_mult=2.0)
    pos = Position("A", qty=10, avg_price=110)
    strat.on_bar(_bar(0, 100, 110, 100, 105), Position("A"))   # seed
    strat.on_bar(_bar(1, 105, 115, 105, 110), pos)             # 보유, TR=10
    strat.on_bar(_bar(2, 110, 120, 110, 115), pos)             # 고점120, TR=10
    # day3: ATR=10, stop=120-10*2=100, 저가 95<=100 → 발동
    signals = strat.on_bar(_bar(3, 100, 105, 95, 98), pos)
    sells = [s for s in signals if s.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].price <= 100  # 스톱가(시가>스톱이므로 스톱가 체결)


def test_gap_down_fills_at_open():
    strat = TrendBreakout(k=0.5, ma_window=1, atr_window=1, trail_mult=2.0)
    pos = Position("A", qty=10, avg_price=110)
    strat.on_bar(_bar(0, 100, 110, 100, 105), Position("A"))   # seed
    strat.on_bar(_bar(1, 105, 115, 105, 110), pos)             # TR=10
    strat.on_bar(_bar(2, 110, 130, 111, 125), pos)             # 고점130, stop=110, 저가111
    # day3: 고점130, ATR=20(day2 TR), stop=130-20*2=90, 시가85가 갭하락 → 시가 체결
    signals = strat.on_bar(_bar(3, 85, 88, 80, 82), pos)
    sells = [s for s in signals if s.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].price == 85
