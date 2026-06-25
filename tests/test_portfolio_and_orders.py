from khali.config import OrderMode
from khali.engine.order_manager import OrderManager
from khali.engine.portfolio import Portfolio


def test_paper_buy_then_sell_profit():
    pf = Portfolio(cash_krw=50000)
    om = OrderManager(OrderMode.PAPER, fee_rate=0.0, portfolio=pf)

    om.buy("KRW-XRP", krw_amount=10000, price=1000)
    assert pf.has_position
    assert pf.coin_volume == 10.0       # 10000 / 1000
    assert pf.cash_krw == 40000
    assert pf.entry_price == 1000

    om.sell("KRW-XRP", volume=10.0, price=1100)
    assert not pf.has_position
    assert pf.cash_krw == 51000          # 40000 + 11000
    assert pf.realized_pnl_total == 1000


def test_fee_reduces_proceeds():
    pf = Portfolio(cash_krw=50000)
    om = OrderManager(OrderMode.PAPER, fee_rate=0.0025, portfolio=pf)
    om.buy("KRW-XRP", krw_amount=10000, price=1000)
    # 수수료 25원만큼 적게 매수됨
    assert round(pf.coin_volume, 6) == round((10000 - 25) / 1000, 6)


def test_consecutive_losses_tracking():
    pf = Portfolio(cash_krw=50000)
    om = OrderManager(OrderMode.PAPER, fee_rate=0.0, portfolio=pf)
    om.buy("KRW-XRP", 10000, 1000)
    om.sell("KRW-XRP", 10.0, 900)   # 손실
    assert pf.consecutive_losses == 1
    om.buy("KRW-XRP", 10000, 1000)
    om.sell("KRW-XRP", 10.0, 1100)  # 수익 -> 리셋
    assert pf.consecutive_losses == 0
