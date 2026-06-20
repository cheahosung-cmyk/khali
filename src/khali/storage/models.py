"""ORM 모델: 거래기록 / 자산 스냅샷."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    market: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(8))      # buy / sell
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    krw: Mapped[float] = mapped_column(Float)         # 투입/회수 금액
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String(10))     # backtest/paper/live
    reason: Mapped[str] = mapped_column(String(200), default="")
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    cash_krw: Mapped[float] = mapped_column(Float)
    position_value: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))
