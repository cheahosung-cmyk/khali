import os
import tempfile
from datetime import datetime, timedelta, timezone

from khali.backtest.rotation import RotationBacktester
from khali.exchange.models import Candle


def _series(prices):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [Candle(base + timedelta(days=i), p, p, p, p, 1.0) for i, p in enumerate(prices)]


def test_rotation_picks_strongest_and_beats_weak(settings):
    n = 200
    strong = _series([100 + i * 2 for i in range(n)])   # 강한 상승
    weak = _series([100 - i * 0.1 for i in range(n)])    # 약한 하락
    btc = _series([100 + i for i in range(n)])           # BTC 상승(불레짐)
    rb = RotationBacktester(settings)
    r = rb.run({"STRONG": strong, "WEAK": weak}, btc,
               lookback=30, rebalance_days=30, regime_ma=20, use_regime=True)
    assert r.total_return_pct > 0           # 상승 코인 따라가 수익
    assert "STRONG" in r.holdings_log


def test_rotation_top_n_holds_multiple(settings):
    n = 200
    a = _series([100 + i * 3 for i in range(n)])    # 강함
    b = _series([100 + i * 2 for i in range(n)])    # 중간
    cc = _series([100 + i * 1 for i in range(n)])   # 약함
    btc = _series([100 + i for i in range(n)])
    rb = RotationBacktester(settings)
    r = rb.run({"A": a, "B": b, "C": cc}, btc,
               lookback=30, rebalance_days=30, regime_ma=20, use_regime=True, top_n=2)
    last = r.holdings_log[-1]            # 상위 2개 동시 보유
    assert "+" in last and len(last.split("+")) == 2
    assert r.final_value > 0


def test_rotation_per_coin_stop_protects_on_crash(settings):
    rise = [100 + i for i in range(51)]                 # 100 -> 150
    crash = [150 * (0.97 ** k) for k in range(1, 70)]   # 급락
    a = _series(rise + crash)
    btc = _series([100 + i for i in range(len(rise) + len(crash))])  # BTC 강세 유지
    rb = RotationBacktester(settings)
    base = dict(lookback=10, rebalance_days=30, regime_ma=5, use_regime=True, top_n=1)
    r_off = rb.run({"A": a}, btc, stop_pct=0.0, **base)
    r_on = rb.run({"A": a}, btc, stop_pct=0.2, **base)
    # 손절 켜면 급락을 일찍 빠져나와 손실이 작다
    assert r_on.final_value > r_off.final_value
    assert "CASH" in r_on.holdings_log


def test_rotation_regime_gate_goes_cash_in_bear(settings):
    n = 200
    coin = _series([100 - i * 0.2 for i in range(n)])
    btc_bear = _series([300 - i for i in range(n)])      # BTC 하락(베어레짐)
    rb = RotationBacktester(settings)
    r = rb.run({"C": coin}, btc_bear, lookback=30, rebalance_days=20,
               regime_ma=20, use_regime=True)
    # 베어 레짐이면 대부분 현금 → 큰 손실 없음
    assert r.cash_ratio_pct > 50
    assert r.total_return_pct > -5


def test_state_persistence_roundtrip():
    from khali.storage.db import init_db
    from khali.storage.repositories import TradeRepository
    from khali.engine.portfolio import Portfolio

    with tempfile.TemporaryDirectory() as d:
        init_db(f"sqlite:///{os.path.join(d, 'state.db')}")
        pf = Portfolio(cash_krw=12345, coin_volume=6.7, entry_price=1800,
                       high_price=1900, realized_pnl_total=300, consecutive_losses=2)
        TradeRepository.save_state(market="KRW-XRP", mode="paper", portfolio=pf)

        # market 불일치 → 복구 안 함 (안전)
        assert TradeRepository.load_state("KRW-ETH", "paper") is None
        # 일치 → 복구
        st = TradeRepository.load_state("KRW-XRP", "paper")
        assert st["cash_krw"] == 12345
        assert st["coin_volume"] == 6.7
        assert st["consecutive_losses"] == 2
