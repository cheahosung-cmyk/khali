from khali.strategies.indicators import rsi, sma


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 5) == 3.0
    assert sma([1, 2], 5) is None


def test_rsi_all_gains_is_100():
    values = list(range(1, 20))
    assert rsi(values, 14) == 100.0


def test_rsi_range():
    values = [10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16]
    val = rsi(values, 14)
    assert val is not None
    assert 0 <= val <= 100
