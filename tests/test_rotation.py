"""로테이션 엔진 테스트 — 항상투자·드롭아웃청산·레짐게이트."""

from datetime import datetime, timedelta

from khali.engine.rotation import run_rotation_backtest
from khali.models import Bar


def _series(symbol, closes):
    return [
        Bar(symbol, datetime(2026, 1, 1) + timedelta(days=i),
            c, c * 1.01, c * 0.99, c, 1000)
        for i, c in enumerate(closes)
    ]


def test_runs_and_invests_in_uptrend():
    # 두 상승 종목, top_n=1 → 더 강한 종목 보유
    uni = {
        "A": _series("A", [100 + i for i in range(80)]),
        "B": _series("B", [100 + i * 2 for i in range(80)]),
    }
    res = run_rotation_backtest(uni, lookback=10, top_n=1, rebalance_days=10)
    assert len(res.equity_curve) == 80
    # 상승장에서 항상 투자하므로 자본이 시작보다 커야 한다
    assert res.end_equity > 10_000_000


def test_no_entry_when_momentum_negative():
    uni = {"D": _series("D", [200 - i for i in range(80)])}  # 하락
    res = run_rotation_backtest(uni, lookback=10, top_n=2, rebalance_days=10)
    # 양의 모멘텀 종목이 없으니 매수 없음 → 자본 불변
    assert res.end_equity == 10_000_000


def test_regime_filter_reduces_drawdown_in_crash():
    # 충분히 긴 상승(MA200 확립) 후 급락 → 레짐 필터가 낙폭을 줄여야 한다
    closes = [100 + i for i in range(260)] + [360 - i * 1.5 for i in range(150)]
    uni = {"A": _series("A", closes), "B": _series("B", closes)}
    with_reg = run_rotation_backtest(uni, lookback=20, top_n=1, rebalance_days=10,
                                     regime_filter=True)
    without = run_rotation_backtest(uni, lookback=20, top_n=1, rebalance_days=10,
                                    regime_filter=False)
    # MDD는 음수 — 레짐 필터판의 낙폭 '크기'가 더 작아야(값이 더 0에 가까움) 한다
    assert with_reg.max_drawdown >= without.max_drawdown
