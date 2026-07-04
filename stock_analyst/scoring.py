"""시장 공통 스코어링: 백분위 랭크 기반 가치·모멘텀·종합 점수."""

import time

import pandas as pd

from . import config


def pctl(series: pd.Series) -> pd.Series:
    """시장 내 백분위 랭크(0~100). NaN은 그대로 NaN."""
    return series.rank(pct=True) * 100


def value_score(df: pd.DataFrame) -> pd.Series:
    """PER·PBR·ROE·배당수익률 백분위 가중합. 컬럼: per, pbr, roe, div."""
    w = config.VALUE_WEIGHTS
    return (
        w["per"] * pctl(1 / df["per"])
        + w["pbr"] * pctl(1 / df["pbr"])
        + w["roe"] * pctl(df["roe"])
        + w["div"] * pctl(df["div"].fillna(0))
    )


def momentum_features(close: pd.Series, volume: pd.Series) -> dict | None:
    """1년 일봉에서 모멘텀 피처 계산. 데이터가 부족하면 None."""
    close = close.dropna()
    volume = volume.reindex(close.index).fillna(0)
    if len(close) < config.MIN_PRICE_ROWS:
        return None
    price = float(close.iloc[-1])
    lo, hi = float(close.min()), float(close.max())
    if hi <= lo or price <= 0:
        return None
    range_pos = min((price - lo) / (hi - lo), config.RANGE_POS_CAP)
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ret60 = price / float(close.iloc[-61]) - 1
    vol60 = float(volume.tail(60).mean())
    vol_ratio = float(volume.tail(20).mean()) / vol60 if vol60 > 0 else 1.0
    return {
        "price": price,
        "range_pos": range_pos,
        "ma_ratio": ma20 / ma60 - 1,
        "ret60": ret60,
        "vol_ratio": vol_ratio,
        "week52_low": lo,
        "week52_high": hi,
    }


def momentum_score(df: pd.DataFrame) -> pd.Series:
    """모멘텀 피처 백분위 가중합. 컬럼: range_pos, ma_ratio, ret60, vol_ratio."""
    w = config.MOMENTUM_WEIGHTS
    return (
        w["range_pos"] * pctl(df["range_pos"])
        + w["ma_ratio"] * pctl(df["ma_ratio"])
        + w["ret60"] * pctl(df["ret60"])
        + w["vol_ratio"] * pctl(df["vol_ratio"])
    )


def composite_score(df: pd.DataFrame) -> pd.Series:
    wv = config.COMPOSITE_VALUE_WEIGHT
    return wv * df["value_score"] + (1 - wv) * df["momentum_score"]


def with_retry(fn, *args, **kwargs):
    """일시적 네트워크 오류 대비 지수 백오프 재시도."""
    last_err = None
    for attempt in range(config.RETRY_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except Exception as err:  # noqa: BLE001 - 데이터 소스 예외 종류가 제각각이라 광범위 캐치
            last_err = err
            time.sleep(config.RETRY_BACKOFF_SECONDS * (2**attempt))
    raise last_err
