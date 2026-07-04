"""KOSPI/KOSDAQ 전 종목 스크리닝 (pykrx).

전 종목 PER/PBR/EPS/BPS/DIV·시총을 시장별 2회 호출로 수집해 가치 점수를 매기고,
가치 상위 종목만 1년 일봉을 개별 조회해 모멘텀 점수를 더한다.
"""

from datetime import datetime, timedelta

import pandas as pd

from . import config
from .scoring import (
    composite_score,
    momentum_features,
    momentum_score,
    value_score,
    with_retry,
)


def screen() -> dict:
    """스크리닝 실행. {"date", "candidates", "scanned", "note"} 반환."""
    from pykrx import stock  # 지연 임포트: --market us 실행 시 불필요한 의존 방지

    today = datetime.now().strftime("%Y%m%d")
    base_date = stock.get_nearest_business_day_in_a_week(today)

    frames = []
    scanned = 0
    for market in config.KR_MARKETS:
        fund = with_retry(stock.get_market_fundamental, base_date, market=market)
        cap = with_retry(stock.get_market_cap, base_date, market=market)
        if fund.empty or cap.empty:
            continue
        df = fund.join(cap, how="inner")
        scanned += len(df)
        df = df.rename(
            columns={
                "PER": "per", "PBR": "pbr", "EPS": "eps", "BPS": "bps", "DIV": "div",
                "시가총액": "market_cap", "거래대금": "trading_value", "종가": "close",
            }
        )
        df["market"] = market
        frames.append(df)

    if not frames:
        return {"date": base_date, "candidates": [], "scanned": 0,
                "note": "KRX 데이터 없음(휴장 또는 수집 실패)"}

    df = pd.concat(frames)
    df.index.name = "ticker"
    df = df.reset_index()

    # 쓰레기 필터: 우선주(끝자리 0 아님)·스팩 제외, 적자·극단 밸류 제거
    df = df[df["ticker"].str.endswith("0")]
    df = df[(df["eps"] > 0) & (df["bps"] > 0)]
    df = df[(df["per"] > 0) & (df["per"] <= config.MAX_PER)]
    df = df[(df["pbr"] > 0) & (df["pbr"] <= config.MAX_PBR)]
    df = df[df["market_cap"] >= config.KR_MIN_MARKET_CAP]
    df = df[df["trading_value"] >= config.KR_MIN_TRADING_VALUE]
    df["roe"] = df["eps"] / df["bps"] * 100
    df = df[df["roe"] >= config.MIN_ROE_PCT]

    names = {t: stock.get_market_ticker_name(t) for t in df["ticker"]}
    df["name"] = df["ticker"].map(names)
    df = df[~df["name"].str.contains("스팩", na=False)]

    # 시장별 백분위가 아닌 KRX 통합 백분위로 가치 점수 산출
    df["value_score"] = value_score(df)
    df = df.sort_values("value_score", ascending=False).head(
        config.KR_VALUE_PREFILTER_N * len(config.KR_MARKETS)
    )

    # 가치 상위 종목만 1년 일봉 조회해 모멘텀 계산
    start = (datetime.strptime(base_date, "%Y%m%d") - timedelta(days=380)).strftime("%Y%m%d")
    feats = {}
    for ticker in df["ticker"]:
        try:
            ohlcv = with_retry(stock.get_market_ohlcv, start, base_date, ticker)
        except Exception:
            continue
        f = momentum_features(ohlcv["종가"], ohlcv["거래량"])
        if f:
            feats[ticker] = f
    feat_df = pd.DataFrame.from_dict(feats, orient="index")
    df = df.set_index("ticker").join(feat_df, how="inner").reset_index()

    if df.empty:
        return {"date": base_date, "candidates": [], "scanned": scanned,
                "note": "필터 통과 종목 없음"}

    df["momentum_score"] = momentum_score(df)
    df["composite_score"] = composite_score(df)
    df = df.sort_values("composite_score", ascending=False).head(config.TOP_N_PER_MARKET)

    candidates = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "market": row.market,
            "price": round(row.price),
            "per": round(row.per, 1),
            "pbr": round(row.pbr, 2),
            "roe_pct": round(row.roe, 1),
            "div_pct": round(row.div, 2),
            "market_cap_krw_bn": round(row.market_cap / 1e9),
            "week52_position": round(row.range_pos, 2),
            "ma20_vs_ma60_pct": round(row.ma_ratio * 100, 1),
            "return_60d_pct": round(row.ret60 * 100, 1),
            "value_score": round(row.value_score, 1),
            "momentum_score": round(row.momentum_score, 1),
            "composite_score": round(row.composite_score, 1),
        }
        for row in df.itertuples()
    ]
    return {"date": base_date, "candidates": candidates, "scanned": scanned, "note": ""}
