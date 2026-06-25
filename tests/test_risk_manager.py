from khali.risk.risk_manager import (
    DayState,
    DecisionType,
    PositionState,
    RiskManager,
)
from khali.strategies.base import Action, Signal


def test_buy_sized_by_position_pct(settings):
    rm = RiskManager(settings)
    d = rm.evaluate(
        Signal(Action.BUY, "test"),
        PositionState(has_position=False),
        current_price=1000,
        day=DayState(capital=50000),
    )
    assert d.type == DecisionType.BUY
    assert d.krw_amount == 25000  # 50000 * 0.5


def test_buy_rejected_below_min_order(settings):
    settings.position_size_pct = 0.05  # 50000*0.05=2500 < 5000
    rm = RiskManager(settings)
    d = rm.evaluate(
        Signal(Action.BUY),
        PositionState(has_position=False),
        current_price=1000,
        day=DayState(capital=50000),
    )
    assert d.type == DecisionType.HOLD


def test_stop_loss_forces_sell(settings):
    rm = RiskManager(settings)
    pos = PositionState(has_position=True, entry_price=1000, volume=10, high_price=1000)
    d = rm.evaluate(
        Signal(Action.HOLD), pos, current_price=970, day=DayState(capital=50000)
    )  # -3% < -2% 손절선
    assert d.type == DecisionType.SELL
    assert "손절" in d.reason
    assert d.volume == 10


def test_take_profit_forces_sell(settings):
    rm = RiskManager(settings)
    pos = PositionState(has_position=True, entry_price=1000, volume=10, high_price=1050)
    d = rm.evaluate(
        Signal(Action.HOLD), pos, current_price=1045, day=DayState(capital=50000)
    )  # +4.5% > +4%
    assert d.type == DecisionType.SELL
    assert "익절" in d.reason


def test_daily_loss_limit_blocks_buy(settings):
    rm = RiskManager(settings)
    # 한도 = -0.1 * 50000 = -5000
    d = rm.evaluate(
        Signal(Action.BUY),
        PositionState(has_position=False),
        current_price=1000,
        day=DayState(capital=50000, realized_pnl_today=-6000),
    )
    assert d.type == DecisionType.HOLD
    assert "한도" in d.reason


def test_consecutive_losses_block_buy(settings):
    rm = RiskManager(settings)
    d = rm.evaluate(
        Signal(Action.BUY),
        PositionState(has_position=False),
        current_price=1000,
        day=DayState(capital=50000, consecutive_losses=3),
    )
    assert d.type == DecisionType.HOLD
    assert "쿨다운" in d.reason
