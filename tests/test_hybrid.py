"""하이브리드(B&H+레짐 방어) 엔진 테스트."""

from datetime import datetime, timedelta

from khali.engine.hybrid import run_hybrid_backtest
from khali.models import Bar


def _series(symbol, closes):
    return [
        Bar(symbol, datetime(2026, 1, 1) + timedelta(days=i),
            c, c * 1.01, c * 0.99, c, 1000)
        for i, c in enumerate(closes)
    ]


def test_invests_in_uptrend():
    # 꾸준한 상승 → MA 위(risk-on) → 보유 → 수익
    closes = [100 + i for i in range(300)]
    uni = {"A": _series("A", closes), "B": _series("B", closes)}
    r = run_hybrid_backtest(uni, ma=100)
    assert r.end_equity > 10_000_000


def test_protects_in_crash_vs_raw_asset():
    # 긴 상승(MA 확립) 후 급락 → 하이브리드가 현금화해 낙폭이 자산 자체보다 작아야 함
    closes = [100 + i for i in range(260)] + [360 - i * 1.5 for i in range(150)]
    uni = {"A": _series("A", closes), "B": _series("B", closes)}
    hybrid = run_hybrid_backtest(uni, ma=100)
    # 원자산 낙폭: 고점 360 → 저점 ~135 ≈ -62%. 하이브리드는 현금화로 훨씬 얕아야 함
    raw_dd = 135 / 360 - 1  # ≈ -0.625
    assert hybrid.max_drawdown > raw_dd + 0.15  # 최소 15%p 이상 방어


def test_runs_over_full_series():
    uni = {"A": _series("A", [100 + (i % 50) for i in range(300)])}
    r = run_hybrid_backtest(uni, ma=100)
    assert len(r.equity_curve) == 300
    assert r.end_equity > 0
