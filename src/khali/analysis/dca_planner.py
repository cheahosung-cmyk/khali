"""현실적 적립식 계획표 — 단일 숫자가 아니라 '범위'로.

과거의 모든 시작 시점(분기마다)에서 같은 적립 계획을 굴려, 결과를 분포로
보여준다. 시작 시점 운(sequence risk)을 정직하게 드러내고, 인플레이션 보정
실질가치와 안전인출(SWR) 월소득까지 함께 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from khali.engine.dca import run_dca
from khali.models import Bar


@dataclass
class PlanOutcome:
    start: datetime
    contributed: float
    final_equity: float
    real_equity: float       # 인플레이션 보정 실질가치
    swr_income: float        # 안전인출 월소득

    @property
    def profit_pct(self) -> float:
        return self.final_equity / self.contributed - 1 if self.contributed else 0.0


def _window(universe: dict[str, list[Bar]], start: datetime, end: datetime):
    return {s: [b for b in bars if start <= b.ts < end]
            for s, bars in universe.items()}


def plan_dca(
    universe: dict[str, list[Bar]],
    initial: float = 1_000_000,
    monthly: float = 300_000,
    horizon_years: int = 5,
    mode: str = "bh",
    infl: float = 0.025,
    swr: float = 0.035,
    step_months: int = 3,
) -> list[PlanOutcome]:
    """가능한 모든 시작 시점(step_months 간격)에서 horizon_years 적립을 굴린다."""
    all_dates = sorted({b.ts for bars in universe.values() for b in bars})
    if not all_dates:
        return []
    first, last = all_dates[0], all_dates[-1]

    outcomes: list[PlanOutcome] = []
    y, m = first.year, first.month
    while True:
        start = datetime(y, m, 1)
        end = datetime(y + horizon_years, m, 1)
        if end > last:
            break
        win = _window(universe, start, end)
        if min((len(b) for b in win.values()), default=0) < horizon_years * 200:
            # 데이터 부족(상장 늦음 등) 구간은 건너뜀
            pass
        else:
            r = run_dca(win, initial=initial, monthly=monthly, mode=mode)
            real = r.final_equity / ((1 + infl) ** horizon_years)
            outcomes.append(PlanOutcome(
                start=start, contributed=r.contributed,
                final_equity=r.final_equity, real_equity=real,
                swr_income=r.final_equity * swr / 12,
            ))
        # step_months 전진
        m += step_months
        while m > 12:
            m -= 12
            y += 1
    return outcomes


def summarize(outcomes: list[PlanOutcome]) -> dict:
    """worst / median / best 분포 요약."""
    if not outcomes:
        return {}
    s = sorted(outcomes, key=lambda o: o.final_equity)
    mid = s[len(s) // 2]
    return {"n": len(s), "worst": s[0], "median": mid, "best": s[-1],
            "contributed": s[0].contributed}
