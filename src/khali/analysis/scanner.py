"""멀티코인 상대강도 스캐너 + 시장(BTC) 레짐 필터.

설계 원칙(토론 합의): '무슨 신호'보다 '언제·무엇을 거래하나'가 수익률을
지배한다. 단일 코인에 고정하지 말고, 시장 레짐이 우호적일 때 가장 강한
코인을 고른다. 베어장에서도 상대적으로 덜 빠지는 코인을 식별해 손실을 줄인다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..exchange.base import ExchangeClient
from ..strategies.indicators import rsi, sma

DEFAULT_BASKET = ["BTC", "ETH", "XRP", "SOL", "ADA", "DOGE", "TRX", "LINK"]


@dataclass
class CoinScore:
    symbol: str
    price: float
    return_30d_pct: float
    vs_ma50_pct: float
    vs_ma200_pct: float
    rsi14: float
    trend: str          # bull / bear / mixed
    score: float        # 상대강도 점수 (높을수록 강함)


def _trend(price: float, ma50: float | None, ma200: float | None) -> str:
    if ma50 and ma200 and price > ma50 > ma200:
        return "bull"
    if ma50 and price < ma50:
        return "bear"
    return "mixed"


def score_market(client: ExchangeClient, symbol: str, payment: str = "KRW") -> CoinScore | None:
    """한 코인의 일봉 상대강도 점수."""
    candles = client.get_candles(f"{payment}-{symbol}", 1440, 250)
    closes = [c.close for c in candles]
    if len(closes) < 31:
        return None
    price = closes[-1]
    ret30 = (price / closes[-31] - 1) * 100
    ma50 = sma(closes, 50)
    ma200 = sma(closes, 200) if len(closes) >= 200 else None
    rsi14 = rsi(closes, 14) or 50.0
    vs50 = (price / ma50 - 1) * 100 if ma50 else 0.0
    vs200 = (price / ma200 - 1) * 100 if ma200 else 0.0
    # 점수: 30일 모멘텀 + MA 대비 위치(추세 정렬) 가중 합
    score = ret30 + vs50 * 0.5 + vs200 * 0.3
    return CoinScore(
        symbol=symbol, price=price, return_30d_pct=ret30,
        vs_ma50_pct=vs50, vs_ma200_pct=vs200, rsi14=rsi14,
        trend=_trend(price, ma50, ma200), score=score,
    )


def scan(
    client: ExchangeClient, symbols: list[str] | None = None, payment: str = "KRW"
) -> list[CoinScore]:
    """바스켓을 상대강도 점수 내림차순으로 정렬해 반환."""
    symbols = symbols or DEFAULT_BASKET
    results = []
    for sym in symbols:
        try:
            s = score_market(client, sym, payment)
            if s:
                results.append(s)
        except Exception:
            continue
    results.sort(key=lambda s: s.score, reverse=True)
    return results


def market_regime(client: ExchangeClient, payment: str = "KRW") -> str:
    """BTC 일봉 기준 시장 전체 레짐. 알트 롱은 BTC가 살아있을 때만 유리."""
    s = score_market(client, "BTC", payment)
    if s is None:
        return "mixed"
    return s.trend
