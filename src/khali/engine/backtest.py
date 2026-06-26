"""백테스트 엔진 — 전략·리스크·페이퍼브로커를 봉 단위로 구동한다.

같은 Strategy/RiskManager 객체가 페이퍼·실거래 엔진에서도 재사용되므로,
여기서 좋은 성과가 나와야 다음 단계(페이퍼)로 진행한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from khali.broker.base import Broker
from khali.broker.paper import PaperBroker
from khali.models import Account, Bar, Order, OrderStatus, OrderType, Position, Side
from khali.risk.manager import RiskManager
from khali.strategy.base import Strategy


def execute_signal(
    broker: Broker,
    risk: RiskManager,
    account: Account,
    bar: Bar,
    signal,
    result: "BacktestResult",
    marks: dict[str, float] | None = None,
) -> None:
    """신호 1개를 리스크 사이징→체결가 클램프→주문→성과 집계까지 처리한다.

    단일종목·포트폴리오 엔진이 공유하는 체결 코어. 체결가는 전략이 정한
    signal.price를 당일 [저,고]로 클램프해 submit에 명시한다(평가 마크는
    종가로 유지되므로 set_mark 토글이 필요 없다). marks는 자본 평가용 전체
    현재가 dict(포트폴리오 사이징 정확도).
    """
    qty = risk.size_order(signal, account, bar.close, marks=marks)
    if qty <= 0:
        return
    fill = max(bar.low, min(signal.price, bar.high))
    order = Order(
        symbol=signal.symbol,
        side=signal.side,
        qty=qty,
        order_type=OrderType.MARKET,
        reason=signal.reason,
        ts=bar.ts,
    )
    filled = broker.submit(order, ref_price=fill)
    if filled.status == OrderStatus.FILLED and signal.side == Side.SELL:
        result.trades += 1
        if filled.realized_pnl > 0:  # 수수료·세금 반영한 순손익 기준 승패
            result.wins += 1


@dataclass
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    trades: int = 0
    wins: int = 0
    start_equity: float = 0.0
    end_equity: float = 0.0

    @property
    def total_return(self) -> float:
        if self.start_equity == 0:
            return 0.0
        return (self.end_equity - self.start_equity) / self.start_equity

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def max_drawdown(self) -> float:
        peak = float("-inf")
        mdd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                mdd = min(mdd, (eq - peak) / peak)
        return mdd

    def summary(self) -> str:
        return (
            f"수익률 {self.total_return:+.2%} | "
            f"거래 {self.trades}회 | 승률 {self.win_rate:.1%} | "
            f"MDD {self.max_drawdown:.2%} | "
            f"최종자본 {self.end_equity:,.0f}"
        )


def run_backtest(
    bars: Iterable[Bar],
    strategy: Strategy,
    starting_cash: float = 10_000_000,
    risk: RiskManager | None = None,
) -> BacktestResult:
    broker = PaperBroker(starting_cash)
    if risk is None:
        from khali.risk.manager import RiskConfig

        risk = RiskManager(RiskConfig(), starting_cash)

    result = BacktestResult(start_equity=starting_cash)

    for bar in bars:
        broker.set_mark(bar.symbol, bar.close)
        account = broker.get_account()
        marks = {bar.symbol: bar.close}
        equity_now = account.equity(marks)

        # 일일 손실 kill-switch (전일 종가자본 대비 당일 자본)
        risk.observe(equity_now, bar.ts.date())

        position = account.positions.get(bar.symbol) or Position(bar.symbol)
        for signal in strategy.on_bar(bar, position):
            execute_signal(broker, risk, account, bar, signal, result, marks)

        result.equity_curve.append(account.equity(marks))

    result.end_equity = result.equity_curve[-1] if result.equity_curve else starting_cash
    return result
