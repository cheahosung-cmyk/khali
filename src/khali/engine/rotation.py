"""횡단면 상대강도 로테이션 백테스트.

전문가 16인 토론 결론: 절대 돌파+트레일링 스톱은 현금 드래그·휩쏘로 광역
시장에서 엣지가 없었다. 대안은 **항상 투자(stay-invested)** 하며 종목 간
상대강도 상위 N개를 동일비중 보유, 월 리밸런스로 갈아타는 로테이션.

- 매 리밸런스: 모멘텀 상위 N = 목표. 목표에서 빠진 보유 종목은 청산,
  새로 든 종목은 동일비중 매수.
- 리밸런스 사이엔 보유 유지(저회전).
- 선택적 레짐 게이트: 시장 프록시(유니버스 균등평균)가 MA200 아래면 전면 현금.

기존 execute_signal(청산·성과집계)·리스크 레이어(kill-switch)를 재사용한다.
"""

from __future__ import annotations

from collections import defaultdict

from khali.analysis.momentum import rank_by_momentum
from khali.broker.paper import PaperBroker
from khali.engine.backtest import BacktestResult, execute_signal
from khali.models import Bar, Order, OrderType, Position, Side, Signal
from khali.risk.manager import RiskConfig, RiskManager


def _market_risk_on(data: dict[str, list[Bar]], ma: int = 200) -> dict:
    """시장 프록시(전 종목 균등평균 종가)가 자기 MA 위인 날짜 → True."""
    by_date = defaultdict(list)
    for bars in data.values():
        for b in bars:
            by_date[b.ts.date()].append(b.close)
    dates = sorted(by_date)
    proxy = [sum(by_date[d]) / len(by_date[d]) for d in dates]
    out = {}
    for i, d in enumerate(dates):
        out[d] = i >= ma and proxy[i] > sum(proxy[i - ma:i]) / ma
    return out


def run_rotation_backtest(
    universe: dict[str, list[Bar]],
    starting_cash: float = 10_000_000,
    lookback: int = 120,
    top_n: int = 3,
    rebalance_days: int = 20,
    risk_config: RiskConfig | None = None,
    regime_filter: bool = False,
) -> BacktestResult:
    broker = PaperBroker(starting_cash)
    risk = RiskManager(risk_config or RiskConfig(), starting_cash)
    histories: dict[str, list[Bar]] = {s: [] for s in universe}

    by_date: dict = defaultdict(dict)
    for sym, bars in universe.items():
        for b in bars:
            by_date[b.ts.date()][sym] = b
    dates = sorted(by_date)

    risk_on = _market_risk_on(universe) if regime_filter else {}
    result = BacktestResult(start_equity=starting_cash)
    marks: dict[str, float] = {}
    since_rebalance = rebalance_days

    for date in dates:
        todays = by_date[date]
        for sym, bar in todays.items():
            marks[sym] = bar.close
            broker.set_mark(sym, bar.close)

        account = broker.get_account()
        halted = risk.observe(account.equity(marks), date)

        if since_rebalance >= rebalance_days:
            since_rebalance = 0
            target = set(rank_by_momentum(histories, lookback, top_n))
            if regime_filter and not risk_on.get(date, False):
                target = set()  # 약세 레짐: 전면 현금

            # 1) 목표에서 빠진 보유 종목 청산
            for sym, pos in list(account.positions.items()):
                if pos.is_open and sym not in target and sym in todays:
                    execute_signal(broker, risk, account, todays[sym],
                                   Signal(sym, Side.SELL, todays[sym].close),
                                   result, marks)

            # 2) 새로 든 종목 동일비중 매수 (kill-switch면 매수 보류)
            if not halted and target:
                held = {s for s, p in account.positions.items() if p.is_open}
                to_buy = [s for s in target if s not in held and s in todays]
                if to_buy:
                    budget = account.equity(marks) / top_n  # 슬롯당 동일비중
                    for sym in to_buy:
                        px = todays[sym].close
                        qty = int(min(budget, account.cash) // (px * 1.005))
                        if qty > 0:
                            broker.submit(
                                Order(symbol=sym, side=Side.BUY, qty=qty,
                                      order_type=OrderType.MARKET, ts=todays[sym].ts),
                                ref_price=px,
                            )
        since_rebalance += 1

        for sym, bar in todays.items():
            histories[sym].append(bar)
        result.equity_curve.append(account.equity(marks))

    result.end_equity = (
        result.equity_curve[-1] if result.equity_curve else starting_cash
    )
    return result
