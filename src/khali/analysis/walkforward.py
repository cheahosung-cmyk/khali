"""워크포워드 OOS 검증.

매 테스트 구간마다, '그 이전(train) 구간'에서만 파라미터를 고르고 '그 다음
(test) 구간'에 적용해 성과를 측정한다. test 구간은 파라미터 선정에 전혀
쓰이지 않으므로 진짜 out-of-sample이다. 이걸 통과해야 곡선맞춤이 아니다.
"""

from __future__ import annotations

from itertools import product

from khali.engine.rotation import run_rotation_backtest
from khali.models import Bar
from khali.risk.manager import RiskConfig


def _dates(data: dict[str, list[Bar]], end_year: int) -> list:
    return sorted({b.ts.date() for bars in data.values() for b in bars
                   if b.ts.year <= end_year})


def _filter(data: dict[str, list[Bar]], end_year: int) -> dict[str, list[Bar]]:
    return {s: [b for b in bars if b.ts.year <= end_year]
            for s, bars in data.items()}


def segment_return(
    data: dict[str, list[Bar]], params: dict, start_year: int, end_year: int,
    cash: float = 10_000_000, risk_config: RiskConfig | None = None,
) -> float:
    """data를 end_year까지 넣고 로테이션을 돌린 뒤, [start_year, end_year]
    구간의 수익률만 잘라 반환(직전 자본 대비). 워밍업 히스토리는 포함된다."""
    sub = _filter(data, end_year)
    r = run_rotation_backtest(sub, starting_cash=cash, risk_config=risk_config,
                              **params)
    dates = _dates(data, end_year)
    curve = r.equity_curve
    if len(curve) != len(dates) or not curve:
        return 0.0
    # 기준 자본 = 구간 시작 직전 마지막 자본
    base = cash
    seg_end_eq = curve[-1]
    for i, d in enumerate(dates):
        if d.year >= start_year:
            base = curve[i - 1] if i > 0 else cash
            break
    return seg_end_eq / base - 1 if base else 0.0


def walk_forward(
    data: dict[str, list[Bar]],
    test_years: list[int],
    train_years: int = 4,
    grid: dict | None = None,
    cash: float = 10_000_000,
    risk_config: RiskConfig | None = None,
) -> list[dict]:
    """각 test_year에 대해: 직전 train_years로 최적 파라미터 선정 → test_year에
    OOS 적용. 연도별 {year, params, oos_return, bh_return}를 반환한다."""
    grid = grid or {"lookback": [120, 180, 252], "top_n": [2, 3, 4],
                    "regime_filter": [False, True]}
    keys = list(grid)
    combos = [dict(zip(keys, vals)) for vals in product(*grid.values())]

    out: list[dict] = []
    for y in test_years:
        tr_start, tr_end = y - train_years, y - 1
        # 1) train 구간에서 최적 파라미터 선정
        best, best_score = None, float("-inf")
        for c in combos:
            s = segment_return(data, c, tr_start, tr_end, cash, risk_config)
            if s > best_score:
                best, best_score = c, s
        # 2) test_year에 OOS 적용
        oos = segment_return(data, best, y, y, cash, risk_config)
        # B&H(test_year, 균등)
        bh = []
        for bars in data.values():
            ys = [b for b in bars if b.ts.year == y]
            if len(ys) > 1:
                bh.append(ys[-1].close / ys[0].close - 1)
        out.append({"year": y, "params": best, "oos_return": oos,
                    "bh_return": sum(bh) / len(bh) if bh else 0.0})
    return out
