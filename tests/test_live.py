"""LiveSession(실시간/페이퍼 루프) 테스트 — 백테스트 코어 재사용 검증."""

from datetime import datetime, timedelta

from khali.broker.paper import PaperBroker
from khali.engine.live import LiveSession
from khali.models import Bar, Position, Side, Signal
from khali.risk.manager import RiskConfig, RiskManager
from khali.strategy.base import Strategy


def _bars(symbol, closes, start=0):
    out = []
    for i, c in enumerate(closes):
        d = datetime(2026, 1, 1) + timedelta(days=start + i)
        out.append(Bar(symbol, d, c, c * 1.01, c * 0.99, c, 1000))
    return out


class BuyOnce(Strategy):
    name = "buy_once"

    def on_bar(self, bar, position):
        if not position.is_open:
            return [Signal(bar.symbol, Side.BUY, bar.close, stop_price=bar.close * 0.95)]
        return []


def _session(symbols, **kw):
    broker = PaperBroker(1_000_000)
    risk = RiskManager(RiskConfig(), 1_000_000)
    return LiveSession(broker, BuyOnce, risk, symbols,
                       lookback=5, top_n=2, rebalance_days=5, **kw), broker


def test_warmup_builds_history_without_trading():
    sess, broker = _session(["A"])
    sess.warmup({"A": _bars("A", [100 + i for i in range(30)])})
    assert len(sess.histories["A"]) == 30
    assert broker.get_account().cash == 1_000_000  # 주문 없음
    assert broker.get_account().positions == {}


def test_step_emits_events_and_trades():
    events = []
    sess, broker = _session(["A"], on_event=events.append)
    sess.warmup({"A": _bars("A", [100 + i for i in range(30)])})
    # 라이브 틱 1일 (상승 종목 → 모멘텀 통과 → 매수)
    nb = _bars("A", [131], start=30)[0]
    sess.step({"A": nb})
    assert any(e["type"] == "fill" and e["side"] == "BUY" for e in events)
    assert broker.get_account().positions["A"].qty > 0


def test_step_no_lookahead_in_rebalance():
    # warmup 없이 첫 step → history 부족으로 모멘텀 선별 비어 매수 불가
    sess, broker = _session(["A"])
    nb = _bars("A", [130], start=0)[0]
    sess.step({"A": nb})
    assert broker.get_account().positions == {}


def test_shares_execute_signal_equity_tracking():
    sess, broker = _session(["A", "B"])
    sess.warmup({
        "A": _bars("A", [100 + i for i in range(30)]),
        "B": _bars("B", [100 + i * 2 for i in range(30)]),
    })
    sess.step({"A": _bars("A", [131], start=30)[0],
               "B": _bars("B", [162], start=30)[0]})
    assert sess.equity > 0
    assert len(sess.result.equity_curve) == 1
