"""이동평균 크로스 전략 테스트."""

from datetime import datetime, timedelta

from khali.models import Bar, Position, Side
from khali.strategy.ma_crossover import MACrossover


def _feed(strat, closes, position):
    """종가 시퀀스를 흘려 발생한 모든 신호를 누적 반환."""
    out = []
    for i, c in enumerate(closes):
        bar = Bar("A", datetime(2026, 1, 1) + timedelta(days=i), c, c, c, c, 1000)
        out.extend(strat.on_bar(bar, position))
    return out


def test_fast_must_be_less_than_slow():
    import pytest
    with pytest.raises(ValueError):
        MACrossover(fast=30, slow=10)


def test_golden_cross_triggers_buy():
    strat = MACrossover(fast=2, slow=4)
    # 하락 후 반등 → 단기MA가 장기MA를 상향 돌파
    closes = [100, 90, 80, 70, 75, 90, 110]
    sig = _feed(strat, closes, Position("A"))
    assert any(s.side == Side.BUY for s in sig)


def test_dead_cross_triggers_sell_when_holding():
    strat = MACrossover(fast=2, slow=4)
    # 상승 후 하락 → 데드크로스, 보유 중이면 청산
    closes = [70, 80, 90, 100, 95, 80, 60]
    pos = Position("A", qty=10, avg_price=90)
    sig = _feed(strat, closes, pos)
    assert any(s.side == Side.SELL for s in sig)


def test_no_signal_during_warmup():
    strat = MACrossover(fast=2, slow=4)
    sig = _feed(strat, [100, 101], Position("A"))
    assert sig == []
