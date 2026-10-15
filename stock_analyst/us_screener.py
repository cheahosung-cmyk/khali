"""미국 주식 스크리닝 (S&P500 + NASDAQ-100 대·중형주).

전 종목(~5천 개) 일일 펀더멘털 수집은 무료 API로 불가능하므로 유니버스를
S&P500 ∪ NASDAQ-100(약 600개)으로 한정한다. 1년 일봉을 벌크 다운로드해
모멘텀으로 프리필터한 뒤, 상위 종목만 yfinance 펀더멘털을 개별 조회한다.
"""

from datetime import datetime, timezone
import math

import pandas as pd

from . import config
from .quality import last_completed_session, utc_now
from .scoring import (
    composite_score,
    momentum_features,
    momentum_score,
    value_score,
    with_retry,
)

UNIVERSE_LABEL = "S&P500 + NASDAQ-100"


def _load_universe() -> pd.DataFrame:
    """티커·이름 유니버스. NASDAQ-100 수집 실패 시 S&P500만으로 진행."""
    import FinanceDataReader as fdr

    sp500 = with_retry(fdr.StockListing, "S&P500")[["Symbol", "Name"]]
    frames = [sp500]
    nasdaq_ok = False
    try:
        nasdaq100 = with_retry(pd.read_html, "https://en.wikipedia.org/wiki/Nasdaq-100")
        for table in nasdaq100:
            if "Ticker" in table.columns:
                frames.append(
                    table.rename(columns={"Ticker": "Symbol", "Company": "Name"})[
                        ["Symbol", "Name"]
                    ]
                )
                nasdaq_ok = True
                break
    except Exception:
        pass  # S&P500만으로 진행
    df = pd.concat(frames).drop_duplicates(subset="Symbol")
    # yfinance 표기 통일 (BRK.B -> BRK-B). FDR은 점을 뗀 표기(BRKB)로 주므로 별도 매핑
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    df["Symbol"] = df["Symbol"].replace({"BRKB": "BRK-B", "BFB": "BF-B"})
    df = df.dropna(subset=["Symbol"])
    df.attrs["universe_label"] = UNIVERSE_LABEL if nasdaq_ok else "S&P500 (NASDAQ-100 목록 미확인)"
    return df


def screen() -> dict:
    import yfinance as yf

    universe = _load_universe()
    tickers = universe["Symbol"].tolist()
    collected_at = utc_now()
    expected = last_completed_session("US", collected_at)
    names = dict(zip(universe["Symbol"], universe["Name"]))
    scanned = len(tickers)
    universe_label = universe.attrs.get("universe_label", "목록 출처 미확인")

    # 1) 벌크 일봉 다운로드 → 전 유니버스 모멘텀 피처
    feats = {}
    last_bar = None
    for i in range(0, len(tickers), config.US_DOWNLOAD_CHUNK):
        chunk = tickers[i : i + config.US_DOWNLOAD_CHUNK]
        try:
            data = with_retry(
                yf.download, chunk, period="1y", interval="1d",
                auto_adjust=True, group_by="ticker", progress=False, threads=True,
            )
        except Exception:
            continue
        for t in chunk:
            try:
                close, volume = data[t]["Close"], data[t]["Volume"]
            except KeyError:
                continue
            close = close.loc[close.index.strftime("%Y-%m-%d") <= expected]
            volume = volume.reindex(close.index)
            f = momentum_features(close, volume)
            if f:
                f["price_date"] = str(close.dropna().index[-1].date())
                feats[t] = f
                idx = close.dropna().index[-1]
                if last_bar is None or idx > last_bar:
                    last_bar = idx

    if not feats:
        return {"date": "", "candidates": [], "scanned": scanned,
                "note": "미국 시세 데이터 수집 실패"}

    price_success = len(feats)
    df = pd.DataFrame.from_dict(feats, orient="index")
    df.index.name = "ticker"
    df["momentum_score"] = momentum_score(df)
    df = df.sort_values("momentum_score", ascending=False).head(
        config.US_MOMENTUM_PREFILTER_N
    )

    fundamental_attempted = len(df)

    # 2) 모멘텀 상위 종목만 펀더멘털 개별 조회
    rows = {}
    info_success = 0
    for t in df.index:
        try:
            info = with_retry(lambda t=t: yf.Ticker(t).info)
        except Exception:
            continue
        if info:
            info_success += 1
        per = info.get("trailingPE")
        pbr = info.get("priceToBook")
        roe = info.get("returnOnEquity")
        cap = info.get("marketCap")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (per, pbr, roe, cap)):
            continue
        # dividendYield는 yfinance 버전에 따라 소수/퍼센트가 갈려서 직접 계산
        rate = info.get("dividendRate")
        price = info.get("currentPrice") or info.get("previousClose") or 0
        rows[t] = {
            "per": per,
            "pbr": pbr,
            "roe": roe * 100,
            "div": rate / price * 100 if rate is not None and price else float("nan"),
            "fundamental_asof": info.get("mostRecentQuarter"),
            "fundamental_collected_at": collected_at,
            "market_cap": cap,
            "sector": info.get("sector", ""),
        }
    fund_df = pd.DataFrame.from_dict(rows, orient="index")
    if fund_df.empty:
        return {"date": str(last_bar.date()), "candidates": [], "scanned": scanned,
                "note": "펀더멘털 수집 실패"}

    quality = {"universe_count": scanned, "price_success": price_success,
               "price_coverage": price_success / scanned if scanned else 0,
               "fundamental_attempted": fundamental_attempted, "fundamental_success": info_success, "fundamental_valid": len(fund_df),
               "fundamental_coverage": info_success / fundamental_attempted if fundamental_attempted else 0}
    df = df.join(fund_df, how="inner").dropna(subset=["div"])

    # 쓰레기 필터 + 밸류트랩 가드
    df = df[(df["per"] > 0) & (df["per"] <= config.MAX_PER)]
    df = df[(df["pbr"] > 0) & (df["pbr"] <= config.MAX_PBR)]
    df = df[df["market_cap"] >= config.US_MIN_MARKET_CAP]
    df = df[df["roe"] >= config.MIN_ROE_PCT]
    if df.empty:
        return {"date": str(last_bar.date()), "candidates": [], "scanned": scanned,
                "note": "필터 통과 종목 없음", "quality": quality}

    # 가치 백분위는 필터 통과 집단 내 상대 순위
    df["value_score"] = value_score(df)
    df["composite_score"] = composite_score(df)
    df = df.sort_values("composite_score", ascending=False).head(config.TOP_N_PER_MARKET)

    note = ""
    stale = (datetime.now(timezone.utc).date() - last_bar.date()).days
    if stale > config.US_STALE_DAYS:
        note = f"마지막 시세가 {stale}일 전 — 휴장 또는 데이터 지연 가능성"

    candidates = [
        {
            "ticker": t,
            "name": names.get(t, t),
            "market": "US",
            "sector": row["sector"],
            "price": round(row["price"], 2),
            "price_date": row["price_date"],
            "price_source": "yfinance auto_adjust=True",
            "fundamental_asof": None if pd.isna(row["fundamental_asof"]) else str(row["fundamental_asof"]),
            "fundamental_collected_at": collected_at,
            "per": round(row["per"], 1),
            "pbr": round(row["pbr"], 2),
            "roe_pct": round(row["roe"], 1),
            "div_pct": round(row["div"], 2),
            "market_cap_usd_bn": round(row["market_cap"] / 1e9, 1),
            "week52_position": round(row["range_pos"], 2),
            "ma20_vs_ma60_pct": round(row["ma_ratio"] * 100, 1),
            "return_60d_pct": round(row["ret60"] * 100, 1),
            "value_score": round(row["value_score"], 1),
            "momentum_score": round(row["momentum_score"], 1),
            "composite_score": round(row["composite_score"], 1),
        }
        for t, row in df.iterrows()
    ]
    return {"date": str(last_bar.date()), "candidates": candidates,
            "scanned": scanned, "note": note, "quality": quality, "universe_label": universe_label}
