"""사전 검증: 추천 후보를 독립 데이터로 교차 확인한다.

퀀트 점수만으로는 "싸 보이는 이유가 있는 종목(가치 함정)"을 거를 수 없으므로,
확정 추천 전에 (1) 증권사 목표주가 컨센서스 대비 상승여력, (2) 최근 뉴스의
악재 신호를 수집해 후보에 붙인다. AI 패널은 이 데이터로 종목별
통과/조건부/탈락 판정을 내린다. 수집은 전부 best-effort — 실패해도
리포트는 계속 만든다.
"""

import requests

from .scoring import with_retry

NAVER_API = "https://m.stock.naver.com/api"
NEWS_PER_TICKER = 5
RISK_KEYWORDS = [
    "유상증자", "감자", "소송", "상장폐지", "관리종목", "횡령", "배임",
    "분식", "감사의견", "회생", "부도", "압수수색", "실적 쇼크", "어닝 쇼크",
]


def _to_float(value) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _flag_news(titles: list[str]) -> list[str]:
    flags = []
    for title in titles:
        for kw in RISK_KEYWORDS:
            if kw in title:
                flags.append(f"뉴스 리스크 의심({kw}): {title}")
                break
    return flags


def _enrich_kr(candidates: list[dict], session: requests.Session) -> None:
    for c in candidates:
        try:
            data = with_retry(
                session.get, f"{NAVER_API}/stock/{c['ticker']}/integration",
                timeout=15,
            ).json()
            target = _to_float((data.get("consensusInfo") or {}).get("priceTargetMean"))
            if target and c["price"]:
                c["analyst_target_price"] = target
                c["target_upside_pct"] = round((target / c["price"] - 1) * 100, 1)
        except Exception:
            pass
        try:
            items = with_retry(
                session.get, f"{NAVER_API}/news/stock/{c['ticker']}",
                params={"pageSize": NEWS_PER_TICKER, "page": 1}, timeout=15,
            ).json()
            titles = [it["title"] for group in items for it in group.get("items", [])]
            if titles:
                c["recent_news"] = titles[:NEWS_PER_TICKER]
                c["warning_flags"] = _flag_news(titles)
        except Exception:
            pass


def _enrich_us(candidates: list[dict]) -> None:
    import yfinance as yf

    for c in candidates:
        try:
            info = with_retry(lambda t=c["ticker"]: yf.Ticker(t).info)
            target = _to_float(info.get("targetMeanPrice"))
            if target and c["price"]:
                c["analyst_target_price"] = target
                c["target_upside_pct"] = round((target / c["price"] - 1) * 100, 1)
                c["analyst_count"] = info.get("numberOfAnalystOpinions")
        except Exception:
            pass
        try:
            news = with_retry(lambda t=c["ticker"]: yf.Ticker(t).news)
            titles = []
            for it in news or []:
                title = it.get("title") or (it.get("content") or {}).get("title")
                if title:
                    titles.append(title)
            if titles:
                c["recent_news"] = titles[:NEWS_PER_TICKER]
        except Exception:
            pass


def enrich(kr: dict, us: dict) -> None:
    """후보 리스트에 검증 데이터를 제자리에서 덧붙인다."""
    if kr.get("candidates"):
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64)"
        _enrich_kr(kr["candidates"], session)
    if us.get("candidates"):
        _enrich_us(us["candidates"])
