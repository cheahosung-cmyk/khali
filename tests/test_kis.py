"""KIS 어댑터 로직 테스트 — 네트워크/실키 없이 가짜 세션으로 검증.

실제 API 호출은 키가 있어야 하므로, 여기서는 토큰 캐시·헤더·주문 바디
구성과 응답 매핑 같은 '우리 코드의 로직'만 검증한다.
"""

import json

import pytest

from khali.broker.kis import KISBroker
from khali.config import KISConfig
from khali.models import Order, OrderStatus, Side


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    """KIS 엔드포인트별 응답을 흉내내고 호출을 기록한다."""

    def __init__(self):
        self.calls = []
        self.token_issues = 0

    def post(self, url, headers=None, json=None, data=None, timeout=None):
        self.calls.append(("POST", url, headers, json, data))
        if url.endswith("/oauth2/tokenP"):
            self.token_issues += 1
            return FakeResp({"access_token": "TOK", "expires_in": 86400})
        if url.endswith("/uapi/hashkey"):
            return FakeResp({"HASH": "HASHED"})
        if url.endswith("/trading/order-cash"):
            return FakeResp({"rt_cd": "0", "msg1": "정상", "output": {"ODNO": "0001"}})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url, headers, params, None))
        if url.endswith("/quotations/inquire-price"):
            return FakeResp({"output": {"stck_prpr": "71000"}})
        if url.endswith("/quotations/inquire-daily-itemchartprice"):
            # KIS는 최신순으로 반환 → daily_bars가 오름차순 정렬해야 한다
            return FakeResp({"output2": [
                {"stck_bsop_date": "20260103", "stck_oprc": "102", "stck_hgpr": "106",
                 "stck_lwpr": "101", "stck_clpr": "105", "acml_vol": "1200"},
                {"stck_bsop_date": "20260102", "stck_oprc": "100", "stck_hgpr": "104",
                 "stck_lwpr": "99", "stck_clpr": "103", "acml_vol": "1000"},
                {"stck_bsop_date": "20260101", "stck_oprc": "0", "stck_hgpr": "0",
                 "stck_lwpr": "0", "stck_clpr": "0", "acml_vol": "0"},  # 거래정지 스킵
            ]})
        if url.endswith("/trading/inquire-balance"):
            return FakeResp({
                "output1": [{"pdno": "005930", "hldg_qty": "10", "pchs_avg_pric": "70000"}],
                "output2": [{"dnca_tot_amt": "5000000"}],
            })
        raise AssertionError(f"unexpected GET {url}")


@pytest.fixture
def broker(tmp_path, monkeypatch):
    # 토큰 캐시를 임시 경로로 돌려 테스트 간 격리
    monkeypatch.setattr("khali.broker.kis._TOKEN_CACHE", tmp_path / "tok.json")
    cfg = KISConfig(app_key="k", app_secret="s", account_no="12345678", is_paper=True)
    b = KISBroker(cfg)
    b._session = FakeSession()
    return b


def test_uses_paper_domain(broker):
    assert "openapivts" in broker.domain  # 모의투자 도메인


def test_token_is_cached_and_reused(broker):
    t1 = broker._ensure_token()
    t2 = broker._ensure_token()
    assert t1 == t2 == "TOK"
    assert broker._session.token_issues == 1  # 재발급 안 함


def test_last_price_parses_output(broker):
    assert broker.last_price("005930") == 71000.0


def test_get_account_builds_positions_and_cash(broker):
    acct = broker.get_account()
    assert acct.cash == 5_000_000
    assert acct.positions["005930"].qty == 10
    assert acct.positions["005930"].avg_price == 70000.0


def test_submit_buy_uses_paper_tr_id_and_accepts(broker):
    order = Order(symbol="005930", side=Side.BUY, qty=3)
    out = broker.submit(order)
    assert out.status == OrderStatus.PENDING
    assert out.broker_order_id == "0001"
    # 주문 POST 호출에서 모의투자 매수 TR_ID 확인
    order_call = [c for c in broker._session.calls if c[1].endswith("order-cash")][0]
    assert order_call[2]["tr_id"] == "VTTC0802U"
    body = json.loads(order_call[4])
    assert body["PDNO"] == "005930" and body["ORD_QTY"] == "3"
    assert body["ORD_DVSN"] == "01"  # 시장가


def test_submit_sell_uses_sell_tr_id(broker):
    broker.submit(Order(symbol="005930", side=Side.SELL, qty=2))
    order_call = [c for c in broker._session.calls if c[1].endswith("order-cash")][0]
    assert order_call[2]["tr_id"] == "VTTC0801U"


def test_daily_bars_parses_and_sorts(broker):
    bars = broker.daily_bars("005930", "20260101", "20260103")
    # 거래정지(거래량 0) 봉은 제외, 오름차순 정렬
    assert len(bars) == 2
    assert bars[0].ts.strftime("%Y%m%d") == "20260102"
    assert bars[1].ts.strftime("%Y%m%d") == "20260103"
    assert bars[1].close == 105.0 and bars[1].open == 102.0
