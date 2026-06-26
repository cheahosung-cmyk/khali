"""핵심 도메인 모델. 외부 의존성 없이 stdlib만 사용한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Bar:
    """일/분 봉 시세 데이터."""

    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        """당일 고저 변동폭."""
        return self.high - self.low


@dataclass
class Signal:
    """전략이 생성하는 매매 신호. 가격은 '의도'이며 실행가는 브로커가 결정."""

    symbol: str
    side: Side
    price: float
    reason: str = ""
    # 전략이 제안하는 손절가(있으면 리스크 매니저가 참고)
    stop_price: float | None = None


@dataclass
class Order:
    symbol: str
    side: Side
    qty: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    filled_price: float = 0.0
    broker_order_id: str | None = None
    reason: str = ""
    ts: datetime | None = None
    # 청산(SELL) 체결 시 실현손익(수수료·세금 반영). 매수는 0.
    realized_pnl: float = 0.0


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.qty != 0

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_price) * self.qty


@dataclass
class Account:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    def equity(self, marks: dict[str, float]) -> float:
        """현금 + 보유 포지션 평가액."""
        pos_value = sum(
            p.market_value(marks.get(sym, p.avg_price))
            for sym, p in self.positions.items()
        )
        return self.cash + pos_value
