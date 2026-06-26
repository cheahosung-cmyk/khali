"""한국투자증권(KIS) OpenAPI 실거래 어댑터 — 실구현.

KIS Developers 스펙대로 OAuth 토큰 발급/캐시, 현재가·잔고 조회, 현금주문을
구현한다. is_paper=True면 모의투자 서버를 가리킨다.

⚠️ 이 모듈은 KIS API 스펙에 맞춰 작성됐으나, 실제 발급 키 없이는 끝단까지
검증할 수 없다. 반드시 **모의투자(KIS_IS_PAPER=true)** 로 충분히 확인한 뒤
실전으로 넘어갈 것. 주문 함수는 실제 체결을 유발하므로 신중히 사용한다.

문서: https://apiportal.koreainvestment.com  (KIS Developers)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from khali.broker.base import Broker
from khali.config import KISConfig
from khali.models import Account, Order, OrderStatus, Position, Side

REAL_DOMAIN = "https://openapi.koreainvestment.com:9443"
PAPER_DOMAIN = "https://openapivts.koreainvestment.com:29443"
_TOKEN_CACHE = Path(".cache/kis_token.json")

# 거래/잔고 TR_ID (실전/모의 구분)
_TR = {
    "balance": {"real": "TTTC8434R", "paper": "VTTC8434R"},
    "buy": {"real": "TTTC0802U", "paper": "VTTC0802U"},
    "sell": {"real": "TTTC0801U", "paper": "VTTC0801U"},
    "price": {"real": "FHKST01010100", "paper": "FHKST01010100"},
}


class KISBroker(Broker):
    def __init__(self, config: KISConfig):
        import requests  # 지연 임포트: 백테스트만 쓸 땐 requests 불필요

        self.config = config
        self.domain = PAPER_DOMAIN if config.is_paper else REAL_DOMAIN
        self._mode = "paper" if config.is_paper else "real"
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------ 인증
    def _ensure_token(self) -> str:
        """OAuth 접근토큰 발급/갱신. 만료 60초 전까지 캐시 재사용.

        KIS는 토큰 발급을 분당 1회로 제한하므로 파일 캐시로 재발급을 줄인다.
        """
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token

        if _TOKEN_CACHE.exists():
            try:
                cached = json.loads(_TOKEN_CACHE.read_text())
                if cached.get("mode") == self._mode and cached["expiry"] > now + 60:
                    self._token = cached["token"]
                    self._token_expiry = cached["expiry"]
                    return self._token
            except (json.JSONDecodeError, KeyError):
                pass

        resp = self._session.post(
            f"{self.domain}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = now + int(data.get("expires_in", 86400))
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(
            json.dumps(
                {"token": self._token, "expiry": self._token_expiry, "mode": self._mode}
            )
        )
        return self._token

    def _headers(self, tr_id: str, hashkey: str | None = None) -> dict:
        h = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey:
            h["hashkey"] = hashkey
        return h

    def _hashkey(self, body: dict) -> str:
        """주문 바디 위변조 방지 해시키 발급."""
        resp = self._session.post(
            f"{self.domain}/uapi/hashkey",
            headers={
                "content-type": "application/json; charset=utf-8",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            data=json.dumps(body),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["HASH"]

    # ------------------------------------------------------------- 시세/잔고
    def last_price(self, symbol: str) -> float:
        """현재가 조회. GET /uapi/domestic-stock/v1/quotations/inquire-price."""
        resp = self._session.get(
            f"{self.domain}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers(_TR["price"][self._mode]),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return float(resp.json()["output"]["stck_prpr"])

    def get_account(self) -> Account:
        """잔고 조회. GET /uapi/domestic-stock/v1/trading/inquire-balance."""
        resp = self._session.get(
            f"{self.domain}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._headers(_TR["balance"][self._mode]),
            params={
                "CANO": self.config.account_no,
                "ACNT_PRDT_CD": self.config.account_product,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        positions: dict[str, Position] = {}
        for row in data.get("output1", []):
            qty = int(row.get("hldg_qty", 0) or 0)
            if qty <= 0:
                continue
            positions[row["pdno"]] = Position(
                symbol=row["pdno"],
                qty=qty,
                avg_price=float(row.get("pchs_avg_pric", 0) or 0),
            )
        summary = data.get("output2", [{}])
        cash = float(summary[0].get("dnca_tot_amt", 0) or 0) if summary else 0.0
        return Account(cash=cash, positions=positions)

    # ----------------------------------------------------------------- 주문
    def submit(self, order: Order) -> Order:
        """현금 주문 전송. POST /uapi/domestic-stock/v1/trading/order-cash.

        ⚠️ 실제 주문이 발생한다. ORD_DVSN '01'=시장가(시장가는 ORD_UNPR='0').
        KIS 응답(rt_cd='0')은 *접수* 성공이며, 실제 체결 확인은 별도 조회가
        필요하다. 여기서는 접수 성공 시 PENDING(접수)으로 표기한다.
        """
        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product,
            "PDNO": order.symbol,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(order.qty),
            "ORD_UNPR": "0",
        }
        tr_id = _TR["buy" if order.side == Side.BUY else "sell"][self._mode]
        hashkey = self._hashkey(body)
        resp = self._session.post(
            f"{self.domain}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._headers(tr_id, hashkey=hashkey),
            data=json.dumps(body),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") == "0":
            order.status = OrderStatus.PENDING  # 접수 성공(체결은 별도 확인)
            order.broker_order_id = data.get("output", {}).get("ODNO")
        else:
            order.status = OrderStatus.REJECTED
            order.reason = data.get("msg1", "주문 거부")
        return order
