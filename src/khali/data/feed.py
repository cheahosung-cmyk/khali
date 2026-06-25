"""시세 피드. 백테스트는 CSV 또는 합성(synthetic) 데이터로 구동한다.

CSV 포맷: ts,open,high,low,close,volume  (헤더 필수)
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from khali.models import Bar

_CACHE_DIR = Path(".cache/naver")


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


def from_naver(
    symbol: str,
    start: str,
    end: str,
    use_cache: bool = True,
) -> list[Bar]:
    """네이버 금융 siseJson API로 실제 일봉을 받아 Bar 리스트로 반환.

    symbol: 6자리 종목코드 (예: 삼성전자 '005930')
    start/end: 'YYYYMMDD'
    결측/0거래량(거래정지 등) 봉은 스킵한다(컴플라이언스 권고).

    requests가 설치되어 있어야 하며, 프록시 환경에선 환경변수의 CA 번들을
    그대로 사용한다(코드에서 TLS 검증을 끄지 않는다).
    """
    cache_file = _CACHE_DIR / f"{symbol}_{start}_{end}.json"
    raw: list | None = None
    if use_cache and cache_file.exists():
        raw = json.loads(cache_file.read_text())
    else:
        import requests

        url = "https://api.finance.naver.com/siseJson.naver"
        params = {
            "symbol": symbol,
            "requestType": "1",
            "startTime": start,
            "endTime": end,
            "timeframe": "day",
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        # 응답은 JSON 유사 텍스트(작은따옴표/개행 포함) → 정규화 후 파싱
        text = resp.text.strip().replace("'", '"')
        raw = json.loads(text)
        if use_cache:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(raw))

    bars: list[Bar] = []
    for row in raw[1:]:  # 0행은 헤더
        date_s, o, h, l, c, vol = row[0], row[1], row[2], row[3], row[4], row[5]
        if not vol or float(vol) == 0:  # 거래정지/결측 스킵
            continue
        bars.append(
            Bar(
                symbol=symbol,
                ts=datetime.strptime(date_s, "%Y%m%d"),
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(vol),
            )
        )
    return bars


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
