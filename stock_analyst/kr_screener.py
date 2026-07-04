"""KOSPI/KOSDAQ 전 종목 스크리닝 (네이버 금융).

KRX 정보데이터시스템(pykrx)은 해외·클라우드 IP를 차단해 GitHub Actions 러너에서
쓸 수 없다. 대신 네이버 금융 시가총액 페이지에서 전 종목의 PER·PBR·ROE·배당금·
시총·거래대금을 수집하고, 가치 상위 종목만 FinanceDataReader(네이버 시세)로
1년 일봉을 조회해 모멘텀 점수를 더한다.
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

from . import config
from .scoring import (
    composite_score,
    momentum_features,
    momentum_score,
    value_score,
    with_retry,
)

BASE = "https://finance.naver.com"
FIELD_IDS = ["market_sum", "amount", "per", "roe", "pbr", "dividend"]
# 페이지 테이블 헤더 → 내부 컬럼명
HEADER_MAP = {
    "현재가": "price",
    "거래대금": "trading_value_mn",  # 백만 원
    "시가총액": "market_cap_100mn",  # 억 원
    "PER": "per",
    "ROE": "roe",
    "PBR": "pbr",
}
MAX_PAGES = 60  # 시장당 50종목/페이지, 안전 상한


def _to_float(text: str) -> float:
    text = text.replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _fetch_market(session: requests.Session, sosok: int, market: str) -> pd.DataFrame:
    rows = []
    for page in range(1, MAX_PAGES + 1):
        resp = with_retry(
            session.get,
            f"{BASE}/sise/sise_market_sum.naver",
            params={"sosok": sosok, "page": page},
            timeout=20,
        )
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.select_one("table.type_2")
        if table is None:
            break
        headers = [th.get_text(strip=True) for th in table.select("tr th")]
        page_rows = 0
        for tr in table.select("tr"):
            link = tr.select_one("a.tltle")
            if link is None:
                continue
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if len(cells) != len(headers):
                continue
            row = {"ticker": link["href"].split("code=")[-1],
                   "name": link.get_text(strip=True), "market": market}
            for header, cell in zip(headers, cells):
                if header in HEADER_MAP:
                    row[HEADER_MAP[header]] = _to_float(cell)
                elif "배당" in header:  # "보통주배당금" (원)
                    row["dps"] = _to_float(cell)
            rows.append(row)
            page_rows += 1
        if page_rows == 0:
            break
        time.sleep(0.2)  # 페이지당 예의상 지연
    return pd.DataFrame(rows)


def screen() -> dict:
    import FinanceDataReader as fdr  # 지연 임포트: --market us 실행 시 불필요한 의존 방지

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
    # 커스텀 필드(PER·ROE·PBR·배당금 등)를 세션에 등록해야 목록 페이지에 표시된다
    with_retry(
        session.post,
        f"{BASE}/sise/field_submit.naver",
        params={"menu": "market_sum",
                "returnUrl": f"{BASE}/sise/sise_market_sum.naver"},
        data=[("fieldIds", f) for f in FIELD_IDS],
        timeout=20,
    )

    frames = [
        _fetch_market(session, sosok, market)
        for sosok, market in [(0, "KOSPI"), (1, "KOSDAQ")]
    ]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
        if any(not f.empty for f in frames) else pd.DataFrame()
    if df.empty:
        return {"date": "-", "candidates": [], "scanned": 0,
                "note": "네이버 금융 데이터 수집 실패"}
    scanned = len(df)

    # 쓰레기 필터: 우선주(끝자리 0 아님)·스팩 제외, 적자·극단 밸류·저유동성 제거
    df = df.dropna(subset=["price", "per", "pbr", "roe", "market_cap_100mn"])
    df = df[df["ticker"].str.endswith("0")]
    df = df[~df["name"].str.contains("스팩", na=False)]
    df = df[(df["per"] > 0) & (df["per"] <= config.MAX_PER)]
    df = df[(df["pbr"] > 0) & (df["pbr"] <= config.MAX_PBR)]
    df = df[df["market_cap_100mn"] * 1e8 >= config.KR_MIN_MARKET_CAP]
    df = df[df["trading_value_mn"].fillna(0) * 1e6 >= config.KR_MIN_TRADING_VALUE]
    df = df[df["roe"] >= config.MIN_ROE_PCT]
    df["div"] = (df["dps"].fillna(0) / df["price"] * 100).clip(lower=0)

    if df.empty:
        return {"date": "-", "candidates": [], "scanned": scanned,
                "note": "필터 통과 종목 없음"}

    # KRX 통합 백분위로 가치 점수 산출 후 상위 종목만 시세 조회
    df["value_score"] = value_score(df)
    df = df.sort_values("value_score", ascending=False).head(
        config.KR_VALUE_PREFILTER_N * 2
    )

    start = (datetime.now() - timedelta(days=380)).strftime("%Y-%m-%d")
    feats = {}
    last_bar = None
    for ticker in df["ticker"]:
        try:
            ohlcv = with_retry(fdr.DataReader, ticker, start)
        except Exception:
            continue
        f = momentum_features(ohlcv["Close"], ohlcv["Volume"])
        if f:
            feats[ticker] = f
            idx = ohlcv["Close"].dropna().index[-1]
            if last_bar is None or idx > last_bar:
                last_bar = idx
    feat_df = pd.DataFrame.from_dict(feats, orient="index")
    df = df.set_index("ticker").join(feat_df, how="inner", rsuffix="_feat")
    df.index.name = "ticker"
    df = df.reset_index()

    if df.empty:
        return {"date": "-", "candidates": [], "scanned": scanned,
                "note": "시세 조회 실패로 모멘텀 계산 불가"}

    df["momentum_score"] = momentum_score(df)
    df["composite_score"] = composite_score(df)
    df = df.sort_values("composite_score", ascending=False).head(config.TOP_N_PER_MARKET)
    base_date = str(last_bar.date()) if last_bar is not None else "-"

    candidates = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "market": row.market,
            "price": round(row.price_feat),  # 일봉 종가 (스냅샷 현재가 대신 기준일 값)
            "per": round(row.per, 1),
            "pbr": round(row.pbr, 2),
            "roe_pct": round(row.roe, 1),
            "div_pct": round(row.div, 2),
            "market_cap_krw_bn": round(row.market_cap_100mn / 10),
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
