from khali.strategies import get_strategy, list_strategies
from khali.strategies.base import Action, StrategyContext


def test_registry_has_defaults():
    names = list_strategies()
    assert "ma_crossover" in names
    assert "rsi_reversion" in names
    assert "volatility_breakout" in names


def test_ma_crossover_golden_cross_buys(candle_factory):
    # 평탄 구간 후 마지막 캔들에서 급등 -> 그 순간 골든크로스 발생
    prices = [100] * 30 + [110]
    ctx = StrategyContext(candles=candle_factory(prices), has_position=False)
    sig = get_strategy("ma_crossover", short=5, long=20).generate_signal(ctx)
    assert sig.action == Action.BUY


def test_rsi_reversion_oversold_buys(candle_factory):
    prices = [100 - i for i in range(20)]  # 지속 하락 -> 과매도
    ctx = StrategyContext(candles=candle_factory(prices), has_position=False)
    sig = get_strategy("rsi_reversion").generate_signal(ctx)
    assert sig.action == Action.BUY


def test_volatility_breakout_buys_on_breakout(candle_factory):
    # 마지막 캔들에서 강한 돌파
    prices = [100, 100, 100, 130]
    candles = candle_factory(prices)
    ctx = StrategyContext(candles=candles, has_position=False)
    sig = get_strategy("volatility_breakout", k=0.5).generate_signal(ctx)
    assert sig.action == Action.BUY
