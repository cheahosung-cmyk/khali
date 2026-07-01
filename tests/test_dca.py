"""적립식(DCA) 시뮬레이터 테스트."""

from datetime import datetime, timedelta

from khali.engine.dca import run_dca
from khali.models import Bar


def _series(symbol, closes, start=0):
    return [
        Bar(symbol, datetime(2020, 1, 1) + timedelta(days=start + i),
            c, c * 1.01, c * 0.99, c, 1000)
        for i, c in enumerate(closes)
    ]


def test_contributions_accumulate():
    # 약 1년(370일)에 걸쳐 매월 적립 → 원금이 초기+12회가량
    uni = {"A": _series("A", [100] * 370)}
    r = run_dca(uni, initial=1_000_000, monthly=100_000, mode="bh")
    # 초기 100만 + 약 12~13개월치 적립
    assert r.contributed >= 1_000_000 + 100_000 * 12


def test_bh_grows_in_uptrend():
    closes = [100 + i for i in range(370)]
    uni = {"A": _series("A", closes)}
    r = run_dca(uni, initial=1_000_000, monthly=100_000, mode="bh")
    # 상승장에서 최종자산 > 납입원금
    assert r.final_equity > r.contributed
    assert r.profit > 0


def test_hybrid_holds_cash_in_downtrend():
    # 충분한 상승 후 급락 → 하이브리드는 현금화로 손실이 bh보다 작아야
    closes = [100 + i for i in range(300)] + [400 - i * 2 for i in range(120)]
    uni = {"A": _series("A", closes), "B": _series("B", closes)}
    bh = run_dca(uni, initial=1_000_000, monthly=100_000, mode="bh", ma=100)
    hy = run_dca(uni, initial=1_000_000, monthly=100_000, mode="hybrid", ma=100)
    # 동일 원금
    assert abs(bh.contributed - hy.contributed) < 1
    # 급락 구간에서 하이브리드 최종자산이 더 크거나 같아야(방어)
    assert hy.final_equity >= bh.final_equity
