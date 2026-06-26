"""시점기준(point-in-time) 멀티종목 포트폴리오 백테스트 엔진.

단일종목 순차 백테스트의 한계(룩어헤드로 종목을 미리 선별)를 제거한다.
- 단일 공유 계좌(현금·포지션을 모든 종목이 공유)
- 매 리밸런스 시점에 **그때까지 완료된 데이터로만** 모멘텀 랭킹 → 상위 N 보유
- 선별에서 빠진 종목은 신규 진입 금지(청산은 항상 허용)
- 자금 배분·동시보유 한도는 공유 RiskManager가 실제로 강제

이로써 종목선별 전략을 미래 정보 유출 없이 정직하게 검증할 수 있다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from khali.analysis.momentum import rank_by_momentum
from khali.broker.paper import PaperBroker
from khali.engine.backtest import BacktestResult
from khali.models import Bar, Order, OrderStatus, OrderType, Position, Side
from khali.risk.manager import RiskConfig, RiskManager
from khali.strategy.base import Strategy


def run_portfolio_backtest(
    universe: dict[str, list[Bar]],
    strategy_factory: Callable[[], Strategy],
    starting_cash: float = 10_000_000,
    risk_config: RiskConfig | None = None,
    lookback: int = 120,
    top_n: int = 3,
    rebalance_days: int = 20,
) -> BacktestResult:
    """포트폴리오 백테스트.

    universe: 종목코드 -> 일봉 리스트
    strategy_factory: 종목마다 독립 상태를 갖는 새 전략 인스턴스를 만드는 함수
    rebalance_days: 리밸런스 주기(거래일). 기본 ~1개월.
    """
    if risk_config is None:
        risk_config = RiskConfig()
    broker = PaperBroker(starting_cash)
    risk = RiskManager(risk_config, starting_cash)
    strategies = {sym: strategy_factory() for sym in universe}
    histories: dict[str, list[Bar]] = {sym: [] for sym in universe}

    # 날짜별로 종목 봉을 모은다 (시간순 정렬의 기준축)
    by_date: dict = defaultdict(dict)
    for sym, bars in universe.items():
        for b in bars:
            by_date[b.ts.date()][sym] = b
    dates = sorted(by_date)

    marks: dict[str, float] = {}
    allowed: set[str] = set()
    since_rebalance = rebalance_days  # 시작 시 곧바로 리밸런스 시도
    result = BacktestResult(start_equity=starting_cash)

    for date in dates:
        # --- 리밸런스: histories는 '오늘 이전'까지만 담겨 있어 룩어헤드 없음 ---
        if since_rebalance >= rebalance_days:
            allowed = set(rank_by_momentum(histories, lookback=lookback, top_n=top_n))
            since_rebalance = 0
        since_rebalance += 1

        todays = by_date[date]
        for sym, bar in todays.items():
            marks[sym] = bar.close

        account = broker.get_account()
        risk.start_new_day(account.equity(marks))
        risk.check_daily_loss(account.equity(marks))

        for sym, bar in todays.items():
            broker.set_mark(sym, bar.close)
            pos = account.positions.get(sym) or Position(sym)
            for sig in strategies[sym].on_bar(bar, pos):
                # 선별에서 빠진 종목은 신규 진입 금지(청산은 허용)
                if sig.side == Side.BUY and sym not in allowed:
                    continue
                qty = risk.size_order(sig, account, bar.close)
                if qty <= 0:
                    continue
                fill = max(bar.low, min(sig.price, bar.high))
                broker.set_mark(sym, fill)
                entry = (
                    account.positions[sym].avg_price
                    if sig.side == Side.SELL and sym in account.positions
                    else fill
                )
                order = Order(
                    symbol=sym, side=sig.side, qty=qty,
                    order_type=OrderType.MARKET, reason=sig.reason, ts=bar.ts,
                )
                filled = broker.submit(order)
                broker.set_mark(sym, bar.close)  # 평가용 복원
                if filled.status == OrderStatus.FILLED and sig.side == Side.SELL:
                    result.trades += 1
                    if filled.filled_price > entry:
                        result.wins += 1

        # 오늘 봉을 history에 반영 (의사결정 이후 → 룩어헤드 차단)
        for sym, bar in todays.items():
            histories[sym].append(bar)
        result.equity_curve.append(broker.get_account().equity(marks))

    result.end_equity = (
        result.equity_curve[-1] if result.equity_curve else starting_cash
    )
    return result
