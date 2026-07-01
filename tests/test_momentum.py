"""모멘텀 종목 선별 단위 테스트."""

from datetime import datetime, timedelta

from khali.analysis.momentum import rank_by_momentum, trailing_return
from khali.models import Bar


def _series(symbol, closes):
    return [
        Bar(symbol, datetime(2026, 1, 1) + timedelta(days=i), c, c, c, c, 1000)
        for i, c in enumerate(closes)
    ]


def test_trailing_return():
    bars = _series("A", [100, 110, 120])
    # lookback 2: 120/100 - 1 = 0.2
    assert abs(trailing_return(bars, 2) - 0.2) < 1e-9


def test_trailing_return_insufficient_data():
    assert trailing_return(_series("A", [100, 110]), 5) is None


def test_rank_selects_top_and_drops_negative():
    universe = {
        "UP": _series("UP", [100, 130]),      # +30%
        "FLAT": _series("FLAT", [100, 105]),  # +5%
        "DOWN": _series("DOWN", [100, 80]),   # -20% (제외)
    }
    ranked = rank_by_momentum(universe, lookback=1, top_n=3)
    assert ranked == ["UP", "FLAT"]  # DOWN은 음수라 제외


def test_rank_respects_top_n():
    universe = {
        "A": _series("A", [100, 140]),
        "B": _series("B", [100, 120]),
        "C": _series("C", [100, 110]),
    }
    assert rank_by_momentum(universe, lookback=1, top_n=2) == ["A", "B"]
