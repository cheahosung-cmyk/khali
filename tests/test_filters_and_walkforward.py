from khali.strategies.base import Action, Signal
from khali.strategies.filters import apply_trend_filter
from khali.backtest.optimizer import Optimizer
from khali.backtest.walkforward import WalkForward


def test_trend_filter_blocks_buy_below_ma():
    closes = [100] * 19 + [80]   # 마지막이 MA20 아래
    sig = apply_trend_filter(Signal(Action.BUY, "x"), closes, ma_period=20)
    assert sig.action == Action.HOLD
    assert "추세필터" in sig.reason


def test_trend_filter_allows_buy_above_ma():
    closes = [100] * 19 + [120]  # 마지막이 MA20 위
    sig = apply_trend_filter(Signal(Action.BUY, "x"), closes, ma_period=20)
    assert sig.action == Action.BUY


def test_trend_filter_off_passes_through():
    closes = [100] * 19 + [80]
    sig = apply_trend_filter(Signal(Action.BUY, "x"), closes, ma_period=0)
    assert sig.action == Action.BUY


def test_trend_filter_never_touches_sell():
    closes = [100] * 19 + [80]
    sig = apply_trend_filter(Signal(Action.SELL, "x"), closes, ma_period=20)
    assert sig.action == Action.SELL


def test_optimize_risk_runs(settings, candle_factory):
    prices = []
    for _ in range(40):
        prices += [100, 104, 108, 103, 99]
    candles = candle_factory(prices)
    rep = Optimizer(settings).optimize_risk(candles, "volatility_breakout")
    assert rep.best is not None
    assert rep.n_combos == 4 * 4 * 3
    assert "stop_loss_pct" in rep.best.params


def test_walkforward_runs(settings, candle_factory):
    prices = []
    for _ in range(200):
        prices += [100, 103, 107, 102, 98]
    candles = candle_factory(prices)  # 1000봉
    rep = WalkForward(settings).run(
        candles, "volatility_breakout", train_size=300, test_size=150
    )
    assert len(rep.folds) >= 1
    assert all("k" in f.best_params for f in rep.folds)
    assert isinstance(rep.summary(), str)
