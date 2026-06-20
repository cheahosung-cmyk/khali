"""테스트 공용 픽스처."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# src 레이아웃 임포트 경로
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from khali.config import OrderMode, Settings  # noqa: E402
from khali.exchange.models import Candle  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        order_mode=OrderMode.BACKTEST,
        market="KRW-XRP",
        base_capital_krw=50000,
        strategy="volatility_breakout",
        position_size_pct=0.5,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
        trailing_stop_pct=0.02,
        daily_loss_limit_pct=0.1,
        max_consecutive_losses=3,
        min_order_krw=5000,
        fee_rate=0.0025,
    )


def make_candles(prices, *, unit_minutes: int = 60) -> list[Candle]:
    """종가 리스트로 캔들 생성 (시/고/저는 단순화)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    prev = prices[0]
    for i, p in enumerate(prices):
        o = prev
        candles.append(
            Candle(
                timestamp=base + timedelta(minutes=unit_minutes * i),
                open=o,
                high=max(o, p) * 1.001,
                low=min(o, p) * 0.999,
                close=p,
                volume=100.0,
            )
        )
        prev = p
    return candles


@pytest.fixture
def candle_factory():
    return make_candles
