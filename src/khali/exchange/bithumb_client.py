"""빗썸 API 2.0 클라이언트 (Upbit 호환 / JWT 인증).

- 공개(시세) 엔드포인트: 인증 불필요
- 비공개(잔고/주문) 엔드포인트: JWT Bearer 토큰
  payload: access_key, nonce(uuid4), timestamp(ms), [query_hash, query_hash_alg]
  서명: HMAC-SHA256 (PyJWT)

주의: 출금(withdraw) 기능은 의도적으로 구현하지 않았습니다. 안전을 위해
발급하는 API 키도 '출금 권한 없이' 발급하세요.
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
import uuid
from datetime import datetime, timezone

import httpx
import jwt

from .models import Balance, Candle, OrderResult, Side, Ticker

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bithumb.com"


class BithumbError(Exception):
    """빗썸 API 오류."""


class BithumbClient:
    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        base_url: str = BASE_URL,
        timeout: float = 10.0,
    ):
        self._access_key = access_key
        self._secret_key = secret_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BithumbClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ────────────────────────── 인증 ──────────────────────────
    def _auth_header(self, params: dict | None = None) -> dict:
        if not self._access_key or not self._secret_key:
            raise BithumbError("API 키가 설정되지 않았습니다 (.env 확인).")

        payload: dict = {
            "access_key": self._access_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": round(time.time() * 1000),
        }
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            payload["query_hash"] = hashlib.sha512(query.encode()).hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = jwt.encode(payload, self._secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self, method: str, path: str, *, params=None, auth=False
    ) -> dict | list:
        headers = self._auth_header(params) if auth else {}
        try:
            if method == "GET":
                resp = self._client.get(path, params=params, headers=headers)
            elif method == "POST":
                headers["Content-Type"] = "application/json"
                resp = self._client.post(path, json=params, headers=headers)
            elif method == "DELETE":
                resp = self._client.delete(path, params=params, headers=headers)
            else:
                raise BithumbError(f"지원하지 않는 메서드: {method}")
        except httpx.HTTPError as e:
            raise BithumbError(f"네트워크 오류: {e}") from e

        if resp.status_code >= 400:
            raise BithumbError(f"{resp.status_code} {path}: {resp.text}")
        return resp.json()

    # ────────────────────── 공개: 시세 ──────────────────────
    def get_ticker(self, market: str) -> Ticker:
        data = self._request("GET", "/v1/ticker", params={"markets": market})
        row = data[0]
        return Ticker(
            market=row["market"],
            trade_price=float(row["trade_price"]),
            timestamp=datetime.now(timezone.utc),
        )

    def get_candles(
        self, market: str, unit: int = 60, count: int = 200
    ) -> list[Candle]:
        """분봉 캔들. unit=1,3,5,10,15,30,60,240."""
        path = f"/v1/candles/minutes/{unit}"
        data = self._request(
            "GET", path, params={"market": market, "count": count}
        )
        return self._parse_candles(data)

    def get_day_candles(self, market: str, count: int = 200) -> list[Candle]:
        data = self._request(
            "GET", "/v1/candles/days", params={"market": market, "count": count}
        )
        return self._parse_candles(data)

    @staticmethod
    def _parse_candles(data: list[dict]) -> list[Candle]:
        candles = [
            Candle(
                timestamp=datetime.fromisoformat(
                    row["candle_date_time_utc"]
                ).replace(tzinfo=timezone.utc),
                open=float(row["opening_price"]),
                high=float(row["high_price"]),
                low=float(row["low_price"]),
                close=float(row["trade_price"]),
                volume=float(row["candle_acc_trade_volume"]),
            )
            for row in data
        ]
        # 빗썸/업비트는 최신 캔들이 먼저 옴 -> 시간 오름차순으로 정렬
        candles.sort(key=lambda c: c.timestamp)
        return candles

    # ────────────────────── 비공개: 계좌/주문 ──────────────────────
    def get_balances(self) -> list[Balance]:
        data = self._request("GET", "/v1/accounts", auth=True)
        return [
            Balance(
                currency=row["currency"],
                balance=float(row["balance"]),
                locked=float(row["locked"]),
                avg_buy_price=float(row.get("avg_buy_price") or 0),
            )
            for row in data
        ]

    def buy_market(self, market: str, krw_amount: float) -> dict:
        """시장가 매수: ord_type=price, price=주문총액(KRW)."""
        params = {
            "market": market,
            "side": Side.BUY.value,
            "ord_type": "price",
            "price": str(krw_amount),
        }
        return self._request("POST", "/v1/orders", params=params, auth=True)

    def sell_market(self, market: str, volume: float) -> dict:
        """시장가 매도: ord_type=market, volume=수량."""
        params = {
            "market": market,
            "side": Side.SELL.value,
            "ord_type": "market",
            "volume": str(volume),
        }
        return self._request("POST", "/v1/orders", params=params, auth=True)

    def get_order(self, order_uuid: str) -> dict:
        return self._request(
            "GET", "/v1/order", params={"uuid": order_uuid}, auth=True
        )

    def cancel_order(self, order_uuid: str) -> dict:
        return self._request(
            "DELETE", "/v1/order", params={"uuid": order_uuid}, auth=True
        )
