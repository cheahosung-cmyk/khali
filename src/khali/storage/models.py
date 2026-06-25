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


class BotState(Base):
    """봇 포지션 상태 (재시작 복구용 싱글턴, id=1)."""

    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(10))
    cash_krw: Mapped[float] = mapped_column(Float)
    coin_volume: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    high_price: Mapped[float] = mapped_column(Float)
    realized_pnl_total: Mapped[float] = mapped_column(Float, default=0.0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    # 로테이션 엔진 복구용: 킬스위치 고점·마지막 리밸런스 시각 (재시작 시 무장해제/churn 방지)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    last_rebalance: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    cash_krw: Mapped[float] = mapped_column(Float)
    position_value: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))
