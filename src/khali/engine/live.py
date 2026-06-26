"""실시간/페이퍼 매매 세션.

백테스트(backtest/portfolio)와 **동일한** execute_signal·모멘텀 게이트·리스크
레이어를 공유하되, 봉을 '도착하는 대로' 하나씩 처리한다. 스케줄러가 매 거래일
장 마감 후 step()을 호출하는 형태로 운용한다.

브로커 중립: PaperBroker(모의)든 KISBroker(실거래)든 동일하게 구동된다.
- warmup(): 과거 봉으로 지표 상태를 구축(주문 없음)
- step(): 하루치 봉을 받아 모멘텀 리밸런스 → 전략 → 리스크 → 체결

이로써 '백테스트에서 검증한 그 코드'가 그대로 페이퍼/실거래를 돌린다.
"""

from __future__ import annotations

from typing import Callable

from khali.analysis.momentum import rank_by_momentum
from khali.broker.base import Broker
from khali.engine.backtest import BacktestResult, execute_signal
from khali.models import Bar, Position, Side
from khali.risk.manager import RiskManager
from khali.strategy.base import Strategy


class LiveSession:
    def __init__(
        self,
        broker: Broker,
        strategy_factory: Callable[[], Strategy],
        risk: RiskManager,
        symbols: list[str],
        lookback: int = 120,
        top_n: int = 3,
        rebalance_days: int = 20,
        on_event: Callable[[dict], None] | None = None,
    ):
        self.broker = broker
        self.risk = risk
        self.symbols = list(symbols)
        self.strategies = {s: strategy_factory() for s in self.symbols}
        self.histories: dict[str, list[Bar]] = {s: [] for s in self.symbols}
        self.lookback = lookback
        self.top_n = top_n
        self.rebalance_days = rebalance_days
        self.on_event = on_event or (lambda e: None)
        self.result = BacktestResult(start_equity=broker.get_account().cash)
        self._marks: dict[str, float] = {}
        self._allowed: set[str] = set()
        self._since_rebalance = rebalance_days
        self.equity = broker.get_account().cash

    def warmup(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        """과거 봉을 시간순으로 전략에 흘려 지표 상태·history를 구축(주문 없음)."""
        dated: list[tuple] = []
        for sym, bars in bars_by_symbol.items():
            for b in bars:
                dated.append((b.ts, sym, b))
        for _ts, sym, b in sorted(dated, key=lambda x: x[0]):
            if sym not in self.strategies:
                continue
            self.strategies[sym].on_bar(b, Position(sym))
            self.histories[sym].append(b)
            self._marks[sym] = b.close
        self.on_event({"type": "warmup_done",
                       "bars": sum(len(v) for v in self.histories.values())})

    def step(self, todays_bars: dict[str, Bar]) -> None:
        """하루치 봉(dict[종목, 봉])을 처리한다. 장 마감 후 1회 호출."""
        if not todays_bars:
            return

        # 모멘텀 리밸런스 (그날까지 완료된 history만 사용 → 룩어헤드 없음)
        if self._since_rebalance >= self.rebalance_days:
            self._allowed = set(
                rank_by_momentum(self.histories, self.lookback, self.top_n)
            )
            self._since_rebalance = 0
            self.on_event({"type": "rebalance", "allowed": sorted(self._allowed)})
        self._since_rebalance += 1

        for sym, bar in todays_bars.items():
            self._marks[sym] = bar.close

        account = self.broker.get_account()
        day = next(iter(todays_bars.values())).ts.date()
        if self.risk.observe(account.equity(self._marks), day):
            self.on_event({"type": "kill_switch", "day": str(day)})

        for sym, bar in todays_bars.items():
            pos = account.positions.get(sym) or Position(sym)
            for sig in self.strategies[sym].on_bar(bar, pos):
                if sig.side == Side.BUY and sym not in self._allowed:
                    continue
                filled = execute_signal(
                    self.broker, self.risk, account, bar, sig, self.result,
                    self._marks,
                )
                if filled is not None:
                    self.on_event({
                        "type": "fill", "symbol": sym, "side": sig.side.value,
                        "qty": filled.filled_qty, "price": filled.filled_price,
                        "reason": sig.reason, "pnl": filled.realized_pnl,
                    })

        for sym, bar in todays_bars.items():
            self.histories[sym].append(bar)
        self.equity = account.equity(self._marks)
        self.result.equity_curve.append(self.equity)
        self.result.end_equity = self.equity
