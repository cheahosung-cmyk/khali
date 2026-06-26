"""리스크 매니저 단위 테스트 — 가장 중요한 안전장치."""

from datetime import date

from khali.models import Account, Position, Side, Signal
from khali.risk.manager import RiskConfig, RiskManager


def _buy(symbol="A", price=100.0, stop=95.0):
    return Signal(symbol, Side.BUY, price, stop_price=stop)


def test_kill_switch_blocks_buys_on_day_over_day_loss():
    rm = RiskManager(RiskConfig(daily_max_loss_pct=0.03), start_equity=1_000_000)
    rm.observe(1_000_000, date(2026, 1, 1))      # 1일차 기준 확립
    rm.observe(950_000, date(2026, 1, 2))        # 전일比 -5% > 3% → 정지
    assert rm.halted
    acct = Account(cash=1_000_000)
    assert rm.size_order(_buy(), acct, price=100.0) == 0


def test_kill_switch_not_triggered_intraday_reset_bug():
    # 매 봉 같은 자본을 주면(일봉 1봉/일) 손실 0 → 정지되지 않아야 정상
    rm = RiskManager(RiskConfig(daily_max_loss_pct=0.03), start_equity=1_000_000)
    rm.observe(1_000_000, date(2026, 1, 1))
    rm.observe(1_000_000, date(2026, 1, 2))
    assert not rm.halted


def test_kill_switch_clears_on_new_day():
    rm = RiskManager(RiskConfig(daily_max_loss_pct=0.03), start_equity=1_000_000)
    rm.observe(1_000_000, date(2026, 1, 1))
    rm.observe(950_000, date(2026, 1, 2))        # 정지
    assert rm.halted
    rm.observe(950_000, date(2026, 1, 3))        # 새 날, 전일比 0% → 해제
    assert not rm.halted


def test_sell_returns_full_position():
    rm = RiskManager(RiskConfig(), start_equity=1_000_000)
    acct = Account(cash=0, positions={"A": Position("A", qty=7, avg_price=100)})
    sig = Signal("A", Side.SELL, 110.0)
    assert rm.size_order(sig, acct, price=110.0) == 7


def test_risk_per_trade_sizing():
    # 자본 1,000,000 * 1% = 10,000 위험. 손절폭 5 → 2,000주가 위험기준.
    # 단, 비중상한 20% = 200,000 / 100 = 2,000주, 현금도 충분.
    rm = RiskManager(
        RiskConfig(risk_per_trade=0.01, max_position_pct=0.20),
        start_equity=1_000_000,
    )
    acct = Account(cash=1_000_000)
    qty = rm.size_order(_buy(price=100, stop=95), acct, price=100.0)
    assert qty == 2000


def test_concentration_cap_limits_qty():
    # 손절폭을 아주 작게 해서 위험기준 수량을 크게 → 비중상한이 binding.
    rm = RiskManager(
        RiskConfig(risk_per_trade=0.50, max_position_pct=0.10),
        start_equity=1_000_000,
    )
    acct = Account(cash=1_000_000)
    qty = rm.size_order(_buy(price=100, stop=99.9), acct, price=100.0)
    # 비중상한 10% = 100,000 / 100 = 1000주
    assert qty == 1000


def test_max_open_positions():
    rm = RiskManager(RiskConfig(max_open_positions=1), start_equity=1_000_000)
    acct = Account(
        cash=1_000_000,
        positions={"X": Position("X", qty=5, avg_price=100)},
    )
    # 이미 1종목 보유 → 신규 종목 매수 차단
    assert rm.size_order(_buy(symbol="A"), acct, price=100.0) == 0
