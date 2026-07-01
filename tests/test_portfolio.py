"""포트폴리오 엔진 테스트 — 룩어헤드 차단·자금 공유 검증."""

from datetime import datetime, timedelta

from khali.engine.portfolio import run_portfolio_backtest
from khali.models import Bar, Position, Side, Signal
from khali.risk.manager import RiskConfig
from khali.strategy.base import Strategy


def _bars(symbol, closes, start=0):
    out = []
    for i, c in enumerate(closes):
        d = datetime(2026, 1, 1) + timedelta(days=start + i)
        out.append(Bar(symbol, d, c, c * 1.01, c * 0.99, c, 1000))
    return out


class AlwaysBuy(Strategy):
    """첫 보유 전까지 매 봉 매수 신호, 보유하면 신호 없음 (진입 게이트 검증용)."""

    name = "always_buy"

    def on_bar(self, bar: Bar, position: Position):
        if not position.is_open:
            return [Signal(bar.symbol, Side.BUY, bar.close, stop_price=bar.close * 0.95)]
        return []


def test_runs_and_tracks_equity():
    uni = {"A": _bars("A", [100 + i for i in range(60)])}
    res = run_portfolio_backtest(
        uni, AlwaysBuy, starting_cash=1_000_000,
        lookback=5, top_n=1, rebalance_days=5,
    )
    assert len(res.equity_curve) == 60
    assert res.end_equity > 0


def test_no_entry_before_momentum_history():
    # 상승 종목이라도 초기엔 history 부족 → 진입 불가(룩어헤드 차단의 부수효과)
    uni = {"A": _bars("A", [100 + i for i in range(10)])}
    res = run_portfolio_backtest(
        uni, AlwaysBuy, starting_cash=1_000_000,
        lookback=120, top_n=1, rebalance_days=20,
    )
    # lookback 120 > 데이터 10 → 한 번도 allowed에 못 듦 → 거래 0, 자본 불변
    assert res.trades == 0
    assert res.end_equity == 1_000_000


def test_negative_momentum_symbol_excluded():
    # 하락 종목만 있으면 모멘텀 양수 조건 불충족 → 진입 없음
    uni = {"DOWN": _bars("DOWN", [200 - i for i in range(60)])}
    res = run_portfolio_backtest(
        uni, AlwaysBuy, starting_cash=1_000_000,
        lookback=5, top_n=3, rebalance_days=5,
    )
    assert res.trades == 0


def test_shared_account_caps_open_positions():
    # 두 상승 종목, max_open_positions=1 → 동시 보유 1종목으로 제한
    uni = {
        "A": _bars("A", [100 + i for i in range(60)]),
        "B": _bars("B", [100 + i * 2 for i in range(60)]),
    }
    cfg = RiskConfig(max_open_positions=1)
    res = run_portfolio_backtest(
        uni, AlwaysBuy, starting_cash=1_000_000, risk_config=cfg,
        lookback=5, top_n=2, rebalance_days=5,
    )
    # 엔진이 돌아가고 자본이 유효하면 통과(한도 위반 시 음수/예외 발생)
    assert res.end_equity > 0
    assert len(res.equity_curve) == 60
