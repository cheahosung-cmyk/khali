"""모멘텀 기반 종목 선별.

전문가 토론(4차)에서 도출: 추세가 강한 종목만 매매하면 약세 종목에서의
손실을 애초에 회피할 수 있다(수익률 우선). 단순·견고한 *추세추종 종목선별*로
과거 lookback 구간 수익률 상위 N개를 고른다.
"""

from __future__ import annotations

from khali.models import Bar


def trailing_return(bars: list[Bar], lookback: int) -> float | None:
    """최근 lookback 봉 기준 수익률. 데이터 부족 시 None."""
    if len(bars) <= lookback:
        return None
    past = bars[-lookback - 1].close
    if past <= 0:
        return None
    return bars[-1].close / past - 1


def rank_by_momentum(
    universe: dict[str, list[Bar]],
    lookback: int = 120,
    top_n: int = 3,
) -> list[str]:
    """유니버스(종목코드 -> 봉 리스트)를 모멘텀으로 정렬해 상위 top_n 반환.

    수익률이 양(+)인 종목만 후보로 둔다(하락 추세 회피).
    """
    scored: list[tuple[str, float]] = []
    for sym, bars in universe.items():
        r = trailing_return(bars, lookback)
        if r is not None and r > 0:
            scored.append((sym, r))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in scored[:top_n]]
