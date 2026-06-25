"""거래/자산 기록 저장·조회."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .db import get_session
from .models import BotState, EquitySnapshot, TradeRecord


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
    def save_state(*, market: str, mode: str, portfolio,
                   peak_equity: float | None = None,
                   last_rebalance=None) -> None:
        with get_session() as s:
            st = s.get(BotState, 1)
            if st is None:
                st = BotState(id=1)
                s.add(st)
            st.market = market
            st.mode = mode
            st.cash_krw = portfolio.cash_krw
            st.coin_volume = portfolio.coin_volume
            st.entry_price = portfolio.entry_price
            st.high_price = portfolio.high_price
            st.realized_pnl_total = portfolio.realized_pnl_total
            st.consecutive_losses = portfolio.consecutive_losses
            if peak_equity is not None:
                st.peak_equity = peak_equity
            if last_rebalance is not None:
                st.last_rebalance = last_rebalance

    @staticmethod
    def load_state(market: str, mode: str) -> dict | None:
        """저장된 상태를 반환. market/mode 가 일치할 때만 (안전)."""
        with get_session() as s:
            st = s.get(BotState, 1)
            if st is None or st.market != market or st.mode != mode:
                return None
            return {
                "cash_krw": st.cash_krw,
                "coin_volume": st.coin_volume,
                "entry_price": st.entry_price,
                "high_price": st.high_price,
                "realized_pnl_total": st.realized_pnl_total,
                "consecutive_losses": st.consecutive_losses,
            }

    @staticmethod
    def load_state_by_mode(mode: str) -> dict | None:
        """mode 만으로 상태 복구 (로테이션 엔진용 — 보유 코인이 바뀌므로)."""
        with get_session() as s:
            st = s.get(BotState, 1)
            if st is None or st.mode != mode:
                return None
            return {
                "market": st.market,
                "cash_krw": st.cash_krw,
                "coin_volume": st.coin_volume,
                "entry_price": st.entry_price,
                "high_price": st.high_price,
                "realized_pnl_total": st.realized_pnl_total,
                "consecutive_losses": st.consecutive_losses,
                "peak_equity": st.peak_equity or 0.0,
                "last_rebalance": st.last_rebalance,
            }

    @staticmethod
    def performance_summary(mode: str) -> dict:
        """forward 성과 집계 (반증 도구). 소표본 과신 방지를 위해 원시 사실만 반환."""
        with get_session() as s:
            trades = s.scalars(
                select(TradeRecord).where(TradeRecord.mode == mode)
                .order_by(TradeRecord.ts)
            ).all()
            snaps = s.scalars(
                select(EquitySnapshot).where(EquitySnapshot.mode == mode)
                .order_by(EquitySnapshot.ts)
            ).all()

        sells = [t for t in trades if t.side == "sell"]
        closed = len(sells)
        wins = sum(1 for t in sells if t.realized_pnl > 0)
        net_realized = sum(t.realized_pnl for t in sells)
        total_fees = sum(t.fee for t in trades)

        # 자산곡선 기반: 기간·MDD·time-in-market
        days = 0
        mdd = 0.0
        in_market_pct = 0.0
        first_val = last_val = 0.0
        if snaps:
            first_val = snaps[0].total_value
            last_val = snaps[-1].total_value
            days = max(0, (snaps[-1].ts - snaps[0].ts).days)
            peak = snaps[0].total_value
            for sn in snaps:
                peak = max(peak, sn.total_value)
                if peak > 0:
                    mdd = min(mdd, (sn.total_value - peak) / peak * 100)
            in_market_pct = (
                sum(1 for sn in snaps if sn.position_value > 1e-9) / len(snaps) * 100
            )
        return {
            "closed_trades": closed,
            "win_rate_pct": (wins / closed * 100) if closed else 0.0,
            "net_realized_pnl": net_realized,
            "total_fees": total_fees,
            "days": days,
            "first_value": first_val,
            "last_value": last_val,
            "max_drawdown_pct": abs(mdd),
            "time_in_market_pct": in_market_pct,
            "n_snapshots": len(snaps),
        }

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
