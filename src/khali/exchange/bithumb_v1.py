"""빗썸 API 1.0 클라이언트 (Connect Key + HMAC-SHA512 서명).

- 공개(시세): GET /public/...  (인증 불필요)
    - 캔들: /public/candlestick/{order}_{payment}/{interval}
      응답 data: [[time_ms, open, close, high, low, volume], ...]  (시/종/고/저 순서 주의)
    - 현재가: /public/ticker/{order}_{payment}
- 비공개(계좌/주문): POST (x-www-form-urlencoded)
    헤더: Api-Key, Api-Sign, Api-Nonce
    서명: base64( hex( HMAC_SHA512( endpoint + \\0 + urlencoded_params + \\0 + nonce ) ) )

주의: 출금 기능은 의도적으로 구현하지 않았습니다. 발급 키도 '출금 권한 없이'.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from datetime import datetime, timezone

import httpx

from .base import ExchangeClient
from .models import Balance, Candle, OrderResult, Side, Ticker
from .ratelimit import RateLimiter

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bithumb.com"

# 분 단위 -> 빗썸 1.0 캔들 인터벌 문자열
_INTERVAL_MAP = {
    1: "1m", 3: "3m", 5: "5m", 10: "10m", 30: "30m",
    60: "1h", 360: "6h", 720: "12h", 1440: "24h",
}


class BithumbV1Error(Exception):
    pass


def _to_pair(market: str) -> tuple[str, str]:
    """'KRW-XRP' -> ('XRP', 'KRW'). 'XRP_KRW' 도 허용."""
    if "-" in market:
        payment, order = market.split("-")
    elif "_" in market:
        order, payment = market.split("_")
    else:
        order, payment = market, "KRW"
    return order.upper(), payment.upper()


class BithumbV1Client(ExchangeClient):
    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        base_url: str = BASE_URL,
        timeout: float = 10.0,
    ):
        self._key = access_key
        self._secret = secret_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._rate = RateLimiter()

    def close(self) -> None:
        self._client.close()

    # ────────────────────── 서명/요청 ──────────────────────
    def _signature(self, endpoint: str, params: dict, nonce: str) -> str:
        query = urllib.parse.urlencode(params)
        data = endpoint + chr(0) + query + chr(0) + nonce
        digest = hmac.new(
            self._secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha512
        ).hexdigest()
        return base64.b64encode(digest.encode("utf-8")).decode("utf-8")

    def _private_post(self, endpoint: str, params: dict | None = None) -> dict:
        if not self._key or not self._secret:
            raise BithumbV1Error("API 키가 설정되지 않았습니다.")
        params = dict(params or {})
        params["endpoint"] = endpoint
        nonce = str(int(time.time() * 1000))
        self._rate.wait()
        headers = {
            "Api-Key": self._key,
            "Api-Nonce": nonce,
            "Api-Sign": self._signature(endpoint, params, nonce),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            resp = self._client.post(endpoint, data=params, headers=headers)
        except httpx.HTTPError as e:
            raise BithumbV1Error(f"네트워크 오류: {e}") from e
        body = resp.json()
        if str(body.get("status")) != "0000":
            raise BithumbV1Error(f"{endpoint} 오류: {body}")
        return body

    def _public_get(self, path: str) -> dict:
        self._rate.wait()
        try:
            resp = self._client.get(path)
        except httpx.HTTPError as e:
            raise BithumbV1Error(f"네트워크 오류: {e}") from e
        body = resp.json()
        if str(body.get("status")) != "0000":
            raise BithumbV1Error(f"{path} 오류: {body}")
        return body

    # ────────────────────── 공개: 시세 ──────────────────────
    def get_candles(self, market: str, unit: int = 60, count: int = 200) -> list[Candle]:
        order, payment = _to_pair(market)
        interval = _INTERVAL_MAP.get(unit, "1h")
        body = self._public_get(f"/public/candlestick/{order}_{payment}/{interval}")
        rows = body["data"]
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc),
                open=float(r[1]),
                close=float(r[2]),
                high=float(r[3]),
                low=float(r[4]),
                volume=float(r[5]),
            )
            for r in rows
        ]
        candles.sort(key=lambda c: c.timestamp)
        return candles[-count:] if count else candles

    def get_ticker(self, market: str) -> Ticker:
        order, payment = _to_pair(market)
        body = self._public_get(f"/public/ticker/{order}_{payment}")
        return Ticker(
            market=market,
            trade_price=float(body["data"]["closing_price"]),
            timestamp=datetime.now(timezone.utc),
        )

    # ────────────────────── 비공개: 계좌/주문 ──────────────────────
    def get_balances(self) -> list[Balance]:
        body = self._private_post("/info/balance", {"currency": "ALL"})
        data = body["data"]
        balances: list[Balance] = []
        # data 키 예: total_krw, available_krw, total_xrp, available_xrp, in_use_xrp
        currencies: set[str] = set()
        for k in data:
            if k.startswith("total_"):
                currencies.add(k[len("total_"):].upper())
        for cur in currencies:
            low = cur.lower()
            total = float(data.get(f"total_{low}") or 0)
            available = float(data.get(f"available_{low}") or 0)
            balances.append(
                Balance(
                    currency=cur,
                    balance=available,
                    locked=max(0.0, total - available),
                    avg_buy_price=0.0,  # 1.0 잔고 API 는 평단 미제공
                )
            )
        return balances

    def execute_buy(self, market: str, krw_amount: float, ref_price: float) -> OrderResult:
        order, payment = _to_pair(market)
        # 1.0 시장가 매수는 'units'(수량) 기준 -> 참고가로 환산
        units = round(krw_amount / ref_price, 4) if ref_price else 0.0
        body = self._private_post(
            "/trade/market_buy",
            {"units": units, "order_currency": order, "payment_currency": payment},
        )
        return OrderResult(
            uuid=str(body.get("order_id", "")),
            market=market,
            side=Side.BUY,
            price=ref_price,
            volume=units,
            paid_krw=units * ref_price,
            fee=units * ref_price * 0.0,  # 실수수료는 체결내역 조회 필요
            created_at=datetime.now(timezone.utc),
            simulated=False,
        )

    def execute_sell(self, market: str, volume: float, ref_price: float) -> OrderResult:
        order, payment = _to_pair(market)
        units = round(volume, 4)
        body = self._private_post(
            "/trade/market_sell",
            {"units": units, "order_currency": order, "payment_currency": payment},
        )
        return OrderResult(
            uuid=str(body.get("order_id", "")),
            market=market,
            side=Side.SELL,
            price=ref_price,
            volume=units,
            paid_krw=units * ref_price,
            fee=0.0,
            created_at=datetime.now(timezone.utc),
            simulated=False,
        )
