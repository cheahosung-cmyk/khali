"""거래소 데이터 전송 객체(DTO)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "bid"   # 매수
    SELL = "ask"  # 매도


@dataclass
class Candle:
    """OHLCV 캔들 한 개."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Ticker:
    market: str
    trade_price: float
    timestamp: datetime


@dataclass
class Balance:
    currency: str        # "KRW", "XRP" ...
    balance: float       # 사용 가능 수량
    locked: float        # 주문 묶인 수량
    avg_buy_price: float  # 평균 매수가

    @property
    def total(self) -> float:
        return self.balance + self.locked


@dataclass
class OrderResult:
    """주문 실행 결과 (실거래/모의 공통)."""

    uuid: str
    market: str
    side: Side
    price: float          # 체결(또는 예상) 단가
    volume: float         # 체결 수량
    paid_krw: float       # 사용 금액 (수수료 포함, 매수 시)
    fee: float
    created_at: datetime
    simulated: bool = False  # paper/backtest 여부
