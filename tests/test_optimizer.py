from khali.backtest.optimizer import Optimizer, _expand_grid, _score
from khali.backtest.backtester import BacktestResult


def test_expand_grid_filters_invalid_ma_combos():
    grid = {"short": [5, 10, 20], "long": [10, 20]}
    combos = _expand_grid(grid, "ma_crossover")
    # short < long 만 허용
    assert all(c["short"] < c["long"] for c in combos)
    assert {"short": 5, "long": 10} in combos
    assert {"short": 20, "long": 10} not in combos


def test_expand_grid_empty_returns_single_default():
    assert _expand_grid({}, "whatever") == [{}]


def test_score_metrics():
    r = BacktestResult(
        strategy="x", initial_capital=1, final_value=1,
        total_return_pct=10.0, max_drawdown_pct=5.0,
        num_trades=4, num_wins=2, win_rate_pct=50.0,
    )
    assert _score(r, "return") == 10.0
    assert _score(r, "calmar") == 10.0 / 5.0
    # 거래 0회면 calmar 0
    r.num_trades = 0
    assert _score(r, "calmar") == 0.0


def test_optimizer_runs_and_splits(settings, candle_factory):
    prices = []
    for _ in range(40):
        prices += [100, 103, 106, 104, 101]
    candles = candle_factory(prices)
    rep = Optimizer(settings).optimize(candles, "volatility_breakout", train_ratio=0.7)
    assert rep.best is not None
    assert rep.n_combos == 7          # k 후보 7개
    assert rep.train_size > 0 and rep.test_size > 0
    assert len(rep.top) <= 5
    # best 는 학습 점수 최댓값
    assert rep.best.score == max(r.score for r in rep.top)
