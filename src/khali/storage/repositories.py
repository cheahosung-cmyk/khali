"""거래/자산 기록 저장·조회."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .db import get_session
from .models import EquitySnapshot, TradeRecord


class TradeRepository:
    @staticmethod
    def add_trade(
        *,
        market: str,
        side: str,
        price: float,
        volume: float,
        krw: float,
        fee: float,
        mode: str,
        reason: str = "",
        realized_pnl: float = 0.0,
    ) -> int:
        with get_session() as s:
            rec = TradeRecord(
                market=market,
                side=side,
                price=price,
                volume=volume,
                krw=krw,
                fee=fee,
                mode=mode,
                reason=reason,
                realized_pnl=realized_pnl,
            )
            s.add(rec)
            s.flush()
            return rec.id

    @staticmethod
    def add_equity(
        *, cash_krw: float, position_value: float, total_value: float, mode: str
    ) -> None:
        with get_session() as s:
            s.add(
                EquitySnapshot(
                    cash_krw=cash_krw,
                    position_value=position_value,
                    total_value=total_value,
                    mode=mode,
                )
            )

    @staticmethod
    def recent_trades(limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.scalars(
                select(TradeRecord).order_by(TradeRecord.id.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "ts": r.ts.isoformat(),
                    "market": r.market,
                    "side": r.side,
                    "price": r.price,
                    "volume": r.volume,
                    "krw": r.krw,
                    "fee": r.fee,
                    "mode": r.mode,
                    "reason": r.reason,
                    "realized_pnl": r.realized_pnl,
                }
                for r in rows
            ]

    @staticmethod
    def realized_pnl_today(mode: str) -> float:
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        with get_session() as s:
            rows = s.scalars(
                select(TradeRecord).where(
                    TradeRecord.ts >= start, TradeRecord.mode == mode
                )
            ).all()
            return sum(r.realized_pnl for r in rows)

    @staticmethod
    def equity_curve(limit: int = 500) -> list[dict]:
        with get_session() as s:
            rows = s.scalars(
                select(EquitySnapshot)
                .order_by(EquitySnapshot.id.desc())
                .limit(limit)
            ).all()
            return [
                {"ts": r.ts.isoformat(), "total": r.total_value} for r in reversed(rows)
            ]
