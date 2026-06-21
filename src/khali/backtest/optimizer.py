"""전략 파라미터 최적화 (그리드 서치 + 과최적화 방지).

방법:
  1. 캔들을 학습(in-sample) / 검증(out-of-sample) 구간으로 분리 (기본 70/30)
  2. 학습 구간에서 모든 파라미터 조합을 백테스트하고 점수로 정렬
  3. 최고 조합을 검증 구간에 적용해 실제 일반화 성능을 확인

점수(metric):
  - return : 총수익률
  - calmar : 수익률 / 최대낙폭 (위험 대비 수익, 기본값)

calmar 를 기본으로 하는 이유: 수익률만 보면 한두 번의 운 좋은 거래에
과최적화되기 쉽다. MDD 로 나눠 '덜 위험하게 번' 조합을 선호한다.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..config import Settings
from ..exchange.models import Candle
from ..strategies import get_strategy
from .backtester import BacktestResult, Backtester


@dataclass
class OptimizeRun:
    params: dict
    train: BacktestResult
    test: BacktestResult
    score: float


@dataclass
class OptimizeReport:
    strategy: str
    metric: str
    best: OptimizeRun | None
    top: list[OptimizeRun] = field(default_factory=list)
    n_combos: int = 0
    train_size: int = 0
    test_size: int = 0


def _score(result: BacktestResult, metric: str) -> float:
    if metric == "return":
        return result.total_return_pct
    # calmar: 거래가 없으면 의미 없으므로 0
    if result.num_trades == 0:
        return 0.0
    mdd = max(result.max_drawdown_pct, 0.5)  # 0 division 방지 + 미세 MDD 과대평가 방지
    return result.total_return_pct / mdd


def _expand_grid(grid: dict[str, list], strategy_name: str) -> list[dict]:
    if not grid:
        return [{}]
    keys = list(grid)
    combos = []
    for values in itertools.product(*(grid[k] for k in keys)):
        combo = dict(zip(keys, values))
        # ma_crossover: short < long 조합만 유효
        if strategy_name == "ma_crossover" and combo["short"] >= combo["long"]:
            continue
        combos.append(combo)
    return combos


class Optimizer:
    def __init__(self, settings: Settings):
        self.s = settings

    def optimize(
        self,
        candles: list[Candle],
        strategy_name: str,
        metric: str = "calmar",
        train_ratio: float = 0.7,
        top_n: int = 5,
    ) -> OptimizeReport:
        split = int(len(candles) * train_ratio)
        train_candles = candles[:split]
        test_candles = candles[split:]

        grid = get_strategy(strategy_name).param_grid()
        combos = _expand_grid(grid, strategy_name)

        bt = Backtester(self.s)
        runs: list[OptimizeRun] = []
        for params in combos:
            train_res = bt.run(train_candles, strategy_name, params)
            test_res = bt.run(test_candles, strategy_name, params)
            runs.append(
                OptimizeRun(
                    params=params,
                    train=train_res,
                    test=test_res,
                    score=_score(train_res, metric),
                )
            )

        # 학습 점수 기준 정렬 (검증 점수는 참고용으로 함께 표시)
        runs.sort(key=lambda r: r.score, reverse=True)
        return OptimizeReport(
            strategy=strategy_name,
            metric=metric,
            best=runs[0] if runs else None,
            top=runs[:top_n],
            n_combos=len(combos),
            train_size=len(train_candles),
            test_size=len(test_candles),
        )
