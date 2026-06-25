from khali.backtest.backtester import Backtester


def test_backtest_runs_and_reports(settings, candle_factory):
    # 톱니파형: 변동성 돌파가 거래를 발생시킴
    prices = []
    for _ in range(10):
        prices += [100, 102, 105, 103, 101]
    candles = candle_factory(prices)

    bt = Backtester(settings)
    result = bt.run(candles, "volatility_breakout")

    assert result.strategy == "volatility_breakout"
    assert result.initial_capital == 50000
    assert result.num_trades >= 0
    assert isinstance(result.summary(), str)
    assert result.max_drawdown_pct >= 0


def test_backtest_all_strategies(settings, candle_factory):
    prices = [100 + (i % 7) * 2 for i in range(120)]
    candles = candle_factory(prices)
    bt = Backtester(settings)
    for name in ("ma_crossover", "rsi_reversion", "volatility_breakout"):
        r = bt.run(candles, name)
        assert r.final_value > 0
