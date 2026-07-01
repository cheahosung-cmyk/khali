"""KIS 라이브 러너 테스트 — 네트워크/실키 없이 가짜 브로커로 배선·안전장치 검증."""

from datetime import datetime, timedelta

import pytest

from khali.config import KISConfig
from khali.engine import live_runner
from khali.models import Account, Bar, OrderStatus, Position, Side


class FakeBroker:
    """KISBroker 대역: 상승 일봉을 돌려주고 주문을 기록한다."""

    def __init__(self, config=None):
        self.account = Account(cash=1_000_000)
        self.orders = []

    def daily_bars(self, symbol, start, end):
        return [
            Bar(symbol, datetime(2026, 1, 1) + timedelta(days=i),
                100 + i, (100 + i) * 1.02, (100 + i) * 0.99, 100 + i, 1000)
            for i in range(40)
        ]

    def get_account(self):
        return self.account

    def last_price(self, symbol):
        return 0.0

    def submit(self, order, ref_price=None):
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.filled_price = ref_price or 0.0
        if order.side == Side.BUY:
            cost = order.filled_price * order.qty
            self.account.cash -= cost
            self.account.positions[order.symbol] = Position(
                order.symbol, order.qty, order.filled_price)
        self.orders.append(order)
        return order


@pytest.fixture(autouse=True)
def patch_broker(monkeypatch):
    monkeypatch.setattr(live_runner, "KISBroker", FakeBroker)


def _cfg(paper=True):
    return KISConfig(app_key="k", app_secret="s", account_no="12345678", is_paper=paper)


def test_live_account_requires_explicit_flag():
    # 실전 계좌 + execute + allow_live 없음 → 거부
    with pytest.raises(RuntimeError):
        live_runner.run_once(_cfg(paper=False), execute=True, allow_live=False,
                             on_event=lambda e: None)


def test_dry_run_places_no_orders():
    events = []
    sess = live_runner.run_once(_cfg(paper=True), execute=False,
                                on_event=events.append, lookback=5, warmup_days=40)
    assert sess.broker.orders == []  # dry-run: 주문 없음
    assert any(e["type"] == "dry_run" for e in events)


def test_execute_paper_submits_orders():
    events = []
    sess = live_runner.run_once(_cfg(paper=True), execute=True,
                                on_event=events.append, lookback=5, warmup_days=40)
    # 상승 종목이라 모멘텀 통과 → 매수 체결 발생
    assert any(o.side == Side.BUY for o in sess.broker.orders)
    assert any(e["type"] == "executed" for e in events)


def test_build_session_splits_today_bar():
    sess, today = live_runner.build_session(_cfg(paper=True), universe=["005930"],
                                            lookback=5, warmup_days=40)
    assert "005930" in today
    # warmup은 마지막(오늘) 봉을 제외 → history 39, 오늘 1
    assert len(sess.histories["005930"]) == 39