"""과거 캔들로 전략 성과를 검증하는 백테스터.

DB 에 의존하지 않고 메모리 안에서 Portfolio + RiskManager + 전략을
시뮬레이션한다. 수익률·MDD(최대낙폭)·승률·거래횟수를 리포트한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import OrderMode, Settings
from ..exchange.models import Candle
from ..engine.order_manager import OrderManager
from ..engine.portfolio import Portfolio
from ..risk.risk_manager import DayState, DecisionType, RiskManager
from ..strategies import get_strategy
from ..strategies.base import StrategyContext
from ..strategies.filters import apply_trend_filter


@dataclass
class BacktestResult:
    strategy: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    num_wins: int
    win_rate_pct: float
    equity_curve: list[float] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[{self.strategy}] 초기 {self.initial_capital:,.0f}원 -> "
            f"최종 {self.final_value:,.0f}원 | "
            f"수익률 {self.total_return_pct:+.2f}% | "
            f"MDD {self.max_drawdown_pct:.2f}% | "
            f"거래 {self.num_trades}회 | 승률 {self.win_rate_pct:.1f}%"
        )


class Backtester:
    def __init__(self, settings: Settings):
        self.s = settings

    def run(
        self,
        candles: list[Candle],
        strategy_name: str | None = None,
        params: dict | None = None,
    ) -> BacktestResult:
        strat_name = strategy_name or self.s.strategy
        strategy = get_strategy(strat_name, **(params or {}))
        portfolio = Portfolio(cash_krw=self.s.base_capital_krw)
        order_mgr = OrderManager(
            OrderMode.BACKTEST,
            self.s.fee_rate,
            portfolio,
            slippage_pct=self.s.slippage_pct,
        )
        risk = RiskManager(self.s)
        closes_all = [c.close for c in candles]

        equity: list[float] = []
        peak = self.s.base_capital_krw
        max_dd = 0.0
        wins = 0
        trades = 0
        sell_count = 0

        # 일자별 실현손익 추적 (일일 손실 한도용)
        day_pnl: dict[str, float] = {}

        start = max(strategy.min_candles(), 2)
        for i in range(start, len(candles)):
            window = candles[: i + 1]
            price = window[-1].close
            day_key = window[-1].timestamp.date().isoformat()
            portfolio.mark_price(price)

            ctx = StrategyContext(
                candles=window,
                has_position=portfolio.has_position,
                entry_price=portfolio.entry_price,
            )
            signal = strategy.generate_signal(ctx)
            signal = apply_trend_filter(
                signal, closes_all[: i + 1], self.s.trend_filter_ma
            )

            day = DayState(
                realized_pnl_today=day_pnl.get(day_key, 0.0),
                consecutive_losses=portfolio.consecutive_losses,
                capital=portfolio.total_value(price),
            )
            decision = risk.evaluate(signal, portfolio.position_state(), price, day)

            if decision.type == DecisionType.BUY:
                order_mgr.buy(self.s.market, decision.krw_amount, price)
                trades += 1
            elif decision.type == DecisionType.SELL:
                entry = portfolio.entry_price
                result = order_mgr.sell(self.s.market, decision.volume, price)
                realized = result.paid_krw - entry * result.volume
                day_pnl[day_key] = day_pnl.get(day_key, 0.0) + realized
                trades += 1
                sell_count += 1
                if realized > 0:
                    wins += 1

            total = portfolio.total_value(price)
            equity.append(total)
            peak = max(peak, total)
            dd = (total - peak) / peak * 100 if peak else 0.0
            max_dd = min(max_dd, dd)

        final_value = equity[-1] if equity else self.s.base_capital_krw
        return BacktestResult(
            strategy=strat_name,
            initial_capital=self.s.base_capital_krw,
            final_value=final_value,
            total_return_pct=(final_value / self.s.base_capital_krw - 1) * 100,
            max_drawdown_pct=abs(max_dd),
            num_trades=trades,
            num_wins=wins,
            win_rate_pct=(wins / sell_count * 100) if sell_count else 0.0,
            equity_curve=equity,
        )
