"""시세 피드. 백테스트는 CSV 또는 합성(synthetic) 데이터로 구동한다.

CSV 포맷: ts,open,high,low,close,volume  (헤더 필수)
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from khali.models import Bar


def from_csv(path: str | Path, symbol: str) -> Iterator[Bar]:
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield Bar(
                symbol=symbol,
                ts=datetime.fromisoformat(row["ts"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0) or 0),
            )


def synthetic(
    symbol: str,
    days: int = 250,
    start_price: float = 50_000,
    drift: float = 0.0008,      # 일 평균 상승률 (현 강세장 모사)
    volatility: float = 0.03,   # 일 변동성 (현 고변동성 모사)
    seed: int = 42,
) -> Iterator[Bar]:
    """추세+고변동성 한국 시장을 모사한 합성 일봉. 백테스트 데모용."""
    rng = random.Random(seed)
    price = start_price
    ts = datetime(2026, 1, 2, 9, 0)
    for _ in range(days):
        ret = drift + rng.gauss(0, volatility)
        open_ = price
        close = max(open_ * (1 + ret), 1.0)
        intraday = abs(rng.gauss(0, volatility)) * open_
        high = max(open_, close) + intraday * 0.5
        low = max(min(open_, close) - intraday * 0.5, 1.0)
        vol = 100_000 * (1 + abs(ret) * 10)
        yield Bar(symbol, ts, round(open_), round(high), round(low),
                  round(close), round(vol))
        price = close
        ts += timedelta(days=1)
