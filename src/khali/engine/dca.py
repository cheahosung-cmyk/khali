"""적립식(DCA) 시뮬레이터 — 매월 일정액을 넣으며 굴린다.

소액 투자자의 현실적 자산형성 경로(수익률이 아니라 적립+시간+복리)를 실데이터로
보여준다. 두 모드:
- "bh": 항상 풀투자(매월 유휴현금을 균등 매수)
- "hybrid": 시장 레짐이 약세면 현금, 강세면 투자(낙폭 방어)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from khali.broker.paper import PaperBroker
from khali.engine.rotation import _market_risk_on
from khali.models import Bar, Order, OrderType, Side


@dataclass
class DCAResult:
    contributed: float = 0.0          # 원금 총 납입액
    final_equity: float = 0.0
    equity_curve: list[float] = field(default_factory=list)

    @property
    def profit(self) -> float:
        return self.final_equity - self.contributed

    @property
    def profit_pct(self) -> float:
        return self.profit / self.contributed if self.contributed else 0.0

    def summary(self) -> str:
        return (f"납입원금 {self.contributed:,.0f}  최종자산 {self.final_equity:,.0f}  "
                f"수익 {self.profit:+,.0f} ({self.profit_pct:+.1%})")


def _deploy(broker: PaperBroker, symbols: list[str], prices: dict[str, float]) -> None:
    """유휴현금을 종목당 균등 예산으로 매수(정수주)."""
    acct = broker.get_account()
    if not symbols or acct.cash <= 0:
        return
    budget = acct.cash / len(symbols)
    for sym in symbols:
        px = prices.get(sym)
        if not px:
            continue
        qty = int(budget // (px * 1.005))
        if qty > 0:
            broker.submit(Order(sym, Side.BUY, qty, OrderType.MARKET),
                          ref_price=px)


def run_dca(
    universe: dict[str, list[Bar]],
    initial: float = 1_000_000,
    monthly: float = 500_000,
    mode: str = "bh",
    ma: int = 252,
) -> DCAResult:
    broker = PaperBroker(initial)
    by_date: dict = defaultdict(dict)
    for sym, bars in universe.items():
        for b in bars:
            by_date[b.ts.date()][sym] = b
    dates = sorted(by_date)
    risk_on = _market_risk_on(universe, ma) if mode == "hybrid" else {}

    res = DCAResult(contributed=initial)
    marks: dict[str, float] = {}
    cur_month = None

    for date in dates:
        todays = by_date[date]
        for sym, bar in todays.items():
            marks[sym] = bar.close
            broker.set_mark(sym, bar.close)
        account = broker.get_account()
        on = risk_on.get(date, True)  # bh는 항상 True

        # 하이브리드 약세 전환 시 전량 현금화
        if mode == "hybrid" and not on:
            for sym, p in list(account.positions.items()):
                if p.is_open and sym in todays:
                    broker.submit(Order(sym, Side.SELL, p.qty, OrderType.MARKET),
                                  ref_price=todays[sym].close)

        # 월초: 적립금 납입 + 투자 가능하면 배치
        if date.month != cur_month:
            cur_month = date.month
            broker.get_account().cash += monthly
            res.contributed += monthly

        if on:  # 강세(또는 bh): 유휴현금 균등 배치
            closes = {s: todays[s].close for s in todays}
            _deploy(broker, list(todays), closes)

        res.equity_curve.append(broker.get_account().equity(marks))

    res.final_equity = res.equity_curve[-1] if res.equity_curve else initial
    return res
