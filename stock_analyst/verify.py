"""최근 뉴스의 성공·실패·기사 없음과 수집 시각을 명시한다."""
from datetime import datetime, timedelta, timezone
import html
import re

import requests
from .scoring import with_retry

NAVER_API = "https://m.stock.naver.com/api"
NEWS_PER_TICKER = 5
NEWS_MAX_DAYS = 7
RISK_KEYWORDS = ["유상증자", "감자", "소송", "상장폐지", "관리종목", "횡령", "배임",
                 "분식", "감사의견", "회생", "부도", "압수수색", "실적 쇼크", "어닝 쇼크",
                 "lawsuit", "fraud", "bankruptcy", "delisting", "restatement", "investigation",
                 "default", "offering", "earnings miss"]


def _to_float(value):
    try:
        import math
        v = float(str(value).replace(",", ""))
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _flag_news(titles):
    return [f"뉴스 리스크 의심: {t}" for t in titles
            if any(k in t.lower() for k in RISK_KEYWORDS)]


def _published(item):
    value = item.get("pubDate") or item.get("datetime") or item.get("providerPublishTime")
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        value = str(value)
        if re.fullmatch(r"\d{14}", value):
            from zoneinfo import ZoneInfo
            return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _set_news(c, items, now):
    articles = []
    for item in items:
        title = item.get("title")
        published = _published(item)
        if title and published and now - timedelta(days=NEWS_MAX_DAYS) <= published <= now:
            articles.append({"title": html.unescape(re.sub(r"<[^>]+>", "", title)),
                             "published_at": published.isoformat(),
                             "url": item.get("url") or item.get("link") or
                                    (item.get("canonicalUrl") or {}).get("url")})
    c["news_status"] = "ok" if articles else "empty_or_undated"
    c["news_articles"] = articles[:NEWS_PER_TICKER]
    c["recent_news"] = [a["title"] for a in c["news_articles"]]
    c["warning_flags"] = _flag_news(c["recent_news"])


def enrich(kr, us):
    now = datetime.now(timezone.utc)
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    for market, result in (("KR", kr), ("US", us)):
        for c in result.get("candidates", []):
            c.update(news_status="failed", target_status="failed", warning_flags=[],
                     verification_collected_at=now.isoformat(), event_status="unverified")
            obj = None
            if market == "US":
                try:
                    import yfinance as yf
                    obj = yf.Ticker(c["ticker"])
                    info = with_retry(lambda: obj.info)
                    target = _to_float(info.get("targetMeanPrice"))
                    c["analyst_count"] = info.get("numberOfAnalystOpinions")
                    c["analyst_target_asof"] = None
                except Exception as err:
                    c["target_error"] = type(err).__name__
                    target = None
            else:
                try:
                    info = with_retry(session.get, f"{NAVER_API}/stock/{c['ticker']}/integration",
                                      timeout=15).json()
                    target = _to_float((info.get("consensusInfo") or {}).get("priceTargetMean"))
                    c["analyst_target_asof"] = None
                except Exception as err:
                    c["target_error"] = type(err).__name__
                    target = None
            if target and c.get("price"):
                c.update(analyst_target_price=target,
                         target_upside_pct=round((target / c["price"] - 1) * 100, 1),
                         target_status="ok_date_unknown")
            try:
                if market == "US":
                    if obj is None:
                        raise ValueError("Ticker 초기화 실패")
                    raw = with_retry(lambda: obj.news) or []
                    items = [it.get("content") or it for it in raw]
                else:
                    raw = with_retry(session.get, f"{NAVER_API}/news/stock/{c['ticker']}",
                                     params={"pageSize": NEWS_PER_TICKER, "page": 1}, timeout=15).json()
                    items = [it for group in raw for it in group.get("items", [])]
                _set_news(c, items, now)
            except Exception as err:
                c["news_error"] = type(err).__name__
