"""Buy&Hold + 레짐 방어 하이브리드.

OOS에서 유일하게 일관된 성질(하락장 방어)을 살리되, 시장 드리프트를 포기하지
않는다: 시장 프록시(유니버스 균등평균)가 MA 위(risk-on)면 전 종목 동일비중
보유, 아래(risk-off)면 전면 현금. 레짐 전환 시에만 매매(저회전).

파라미터가 사실상 MA 윈도우 하나뿐이라 과최적화 여지가 작다.
"""

from __future__ import annotations

from collections import defaultdict

from khali.broker.paper import PaperBroker
from khali.engine.backtest import BacktestResult, execute_signal
from khali.engine.rotation import _market_risk_on
from khali.models import Bar, Order, OrderType, Side, Signal
from khali.risk.manager import RiskConfig, RiskManager


def run_hybrid_backtest(
    universe: dict[str, list[Bar]],
    starting_cash: float = 10_000_000,
    ma: int = 200,
    risk_config: RiskConfig | None = None,
) -> BacktestResult:
    broker = PaperBroker(starting_cash)
    risk = RiskManager(risk_config or RiskConfig(), starting_cash)

    by_date: dict = defaultdict(dict)
    for sym, bars in universe.items():
        for b in bars:
            by_date[b.ts.date()][sym] = b
    dates = sorted(by_date)
    risk_on = _market_risk_on(universe, ma)

    result = BacktestResult(start_equity=starting_cash)
    marks: dict[str, float] = {}

    for date in dates:
        todays = by_date[date]
        for sym, bar in todays.items():
            marks[sym] = bar.close
            broker.set_mark(sym, bar.close)

        account = broker.get_account()
        held = {s for s, p in account.positions.items() if p.is_open}
        on = risk_on.get(date, False)

        if on and not held:
            # risk-on 진입: 오늘 거래되는 전 종목 동일비중 매수
            syms = list(todays)
            budget = account.equity(marks) / len(syms)
            for sym in syms:
                px = todays[sym].close
                qty = int(min(budget, account.cash) // (px * 1.005))
                if qty > 0:
                    broker.submit(
                        Order(symbol=sym, side=Side.BUY, qty=qty,
                              order_type=OrderType.MARKET, ts=todays[sym].ts),
                        ref_price=px,
                    )
        elif not on and held:
            # risk-off 전환: 전량 청산(현금)
            for sym in list(held):
                if sym in todays:
                    execute_signal(broker, risk, account, todays[sym],
                                   Signal(sym, Side.SELL, todays[sym].close),
                                   result, marks)

        result.equity_curve.append(account.equity(marks))

    result.end_equity = (
        result.equity_curve[-1] if result.equity_curve else starting_cash
    )
    return result
