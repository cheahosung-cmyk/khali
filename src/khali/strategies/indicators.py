"""기술적 지표 계산 (의존성 없이 numpy 만 사용)."""

from __future__ import annotations

import numpy as np


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return float(np.mean(values[-period:]))


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    arr = np.asarray(values, dtype=float)
    deltas = np.diff(arr[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))
