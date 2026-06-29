"""적립식 계획표(범위) 테스트."""

from datetime import datetime, timedelta

from khali.analysis.dca_planner import plan_dca, summarize
from khali.models import Bar


def _series(symbol, n, start_year=2015, fn=lambda i: 100 + i):
    return [
        Bar(symbol, datetime(start_year, 1, 1) + timedelta(days=i),
            fn(i), fn(i) * 1.01, fn(i) * 0.99, fn(i), 1000)
        for i in range(n)
    ]


def test_produces_multiple_start_windows():
    # 약 6년치 일봉 → 3년 horizon 이면 여러 시작 시점이 나와야
    uni = {"A": _series("A", 6 * 260)}
    outs = plan_dca(uni, horizon_years=3, monthly=100_000, step_months=6)
    assert len(outs) >= 3


def test_summary_orders_worst_to_best():
    uni = {"A": _series("A", 6 * 260)}
    outs = plan_dca(uni, horizon_years=3, monthly=100_000, step_months=6)
    s = summarize(outs)
    assert s["worst"].final_equity <= s["median"].final_equity <= s["best"].final_equity
    assert s["n"] == len(outs)


def test_real_value_below_nominal():
    uni = {"A": _series("A", 6 * 260)}
    outs = plan_dca(uni, horizon_years=3, monthly=100_000, infl=0.025)
    # 인플레이션 보정 실질가치는 명목보다 작아야
    assert all(o.real_equity < o.final_equity for o in outs)


def test_empty_universe():
    assert plan_dca({}, horizon_years=3) == []
    assert summarize([]) == {}
