"""워크포워드 분석 (Walk-Forward Analysis).

과최적화를 가장 엄격하게 검증하는 방법. 데이터를 여러 구간(fold)으로 나눠
각 구간마다:
  1. 학습 윈도우에서 최적 파라미터를 새로 찾고
  2. 바로 다음(미학습) 검증 윈도우에 적용해 성과를 기록
모든 검증 구간 수익을 이어붙이면 '실제로 굴렸다면' 의 근사 성과가 된다.

매 구간 재최적화하므로 단일 백테스트보다 훨씬 현실적이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings
from ..exchange.models import Candle
from .backtester import Backtester
from .optimizer import _expand_grid, _score
from ..strategies import get_strategy


@dataclass
class Fold:
    index: int
    train_start: str
    test_start: str
    test_end: str
    best_params: dict
    train_return_pct: float
    test_return_pct: float
    test_mdd_pct: float
    test_trades: int


@dataclass
class WalkForwardReport:
    strategy: str
    metric: str
    folds: list[Fold] = field(default_factory=list)
    oos_compound_return_pct: float = 0.0   # 검증구간 누적(복리) 수익률
    avg_test_return_pct: float = 0.0
    pct_profitable_folds: float = 0.0

    def summary(self) -> str:
        return (
            f"[{self.strategy}] 워크포워드 {len(self.folds)}구간 | "
            f"누적(복리) {self.oos_compound_return_pct:+.2f}% | "
            f"구간평균 {self.avg_test_return_pct:+.2f}% | "
            f"수익구간 비율 {self.pct_profitable_folds:.0f}%"
        )


class WalkForward:
    def __init__(self, settings: Settings):
        self.s = settings

    def _best_params(self, train: list[Candle], strategy_name: str, metric: str) -> dict:
        grid = get_strategy(strategy_name).param_grid()
        combos = _expand_grid(grid, strategy_name)
        bt = Backtester(self.s)
        best, best_score = {}, float("-inf")
        for params in combos:
            res = bt.run(train, strategy_name, params)
            sc = _score(res, metric)
            if sc > best_score:
                best, best_score = params, sc
        return best

    def run(
        self,
        candles: list[Candle],
        strategy_name: str,
        train_size: int,
        test_size: int,
        metric: str = "calmar",
    ) -> WalkForwardReport:
        bt = Backtester(self.s)
        folds: list[Fold] = []
        compound = 1.0
        i = 0
        idx = 0
        while i + train_size + test_size <= len(candles):
            train = candles[i : i + train_size]
            test = candles[i + train_size : i + train_size + test_size]

            best = self._best_params(train, strategy_name, metric)
            train_res = bt.run(train, strategy_name, best)
            test_res = bt.run(test, strategy_name, best)

            compound *= 1 + test_res.total_return_pct / 100
            folds.append(
                Fold(
                    index=idx,
                    train_start=train[0].timestamp.date().isoformat(),
                    test_start=test[0].timestamp.date().isoformat(),
                    test_end=test[-1].timestamp.date().isoformat(),
                    best_params=best,
                    train_return_pct=train_res.total_return_pct,
                    test_return_pct=test_res.total_return_pct,
                    test_mdd_pct=test_res.max_drawdown_pct,
                    test_trades=test_res.num_trades,
                )
            )
            i += test_size  # 비앵커 롤링
            idx += 1

        n = len(folds)
        avg = sum(f.test_return_pct for f in folds) / n if n else 0.0
        wins = sum(1 for f in folds if f.test_return_pct > 0)
        return WalkForwardReport(
            strategy=strategy_name,
            metric=metric,
            folds=folds,
            oos_compound_return_pct=(compound - 1) * 100,
            avg_test_return_pct=avg,
            pct_profitable_folds=(wins / n * 100) if n else 0.0,
        )
