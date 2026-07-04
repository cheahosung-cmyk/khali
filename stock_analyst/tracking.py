"""추천 성과 추적: 과거 추천 종목의 이후 수익률을 시장 지수와 비교해 검증한다.

매 실행마다 그날의 추천을 reports/history/YYYY-MM-DD.json으로 남기고,
다음 실행부터 과거 추천의 실제 수익률·시장 대비 초과수익을 집계해
"지난 추천 성적표" 섹션을 만든다.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from .scoring import with_retry

MIN_EVAL_DAYS = 5    # 추천 후 최소 5일(달력) 지나야 성과 평가 대상
MAX_DETAIL_ROWS = 12  # 상세 표에 보여줄 최근 추천 수
BENCHMARKS = {"KR": "KS11", "US": "^GSPC"}  # KOSPI, S&P500


def save_snapshot(history_dir: str, date: str, kr: dict, us: dict) -> None:
    """오늘의 추천을 검증용 JSON으로 저장(같은 날 재실행 시 덮어씀)."""
    records = []
    for market, result in (("KR", kr), ("US", us)):
        for c in result.get("candidates", []):
            records.append({
                "market": market,
                "ticker": str(c["ticker"]),
                "name": c["name"],
                "price": c["price"],
                "composite_score": c.get("composite_score"),
            })
    if not records:
        return
    path = Path(history_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{date}.json").write_text(
        json.dumps({"date": date, "candidates": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def _load_history(history_dir: str, today: str) -> list[dict]:
    entries = []
    for f in sorted(Path(history_dir).glob("????-??-??.json")):
        if f.stem >= today:
            continue  # 오늘 것은 평가 대상이 아님
        try:
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return entries


def _kr_price_series(ticker: str, start: str):
    import FinanceDataReader as fdr

    return with_retry(fdr.DataReader, ticker, start)["Close"].dropna()


def _us_price_series(tickers: list[str], start: str) -> dict:
    import yfinance as yf

    if not tickers:
        return {}
    data = with_retry(
        yf.download, tickers, start=start, interval="1d",
        auto_adjust=True, group_by="ticker", progress=False, threads=True,
    )
    out = {}
    for t in tickers:
        try:
            series = (data[t]["Close"] if len(tickers) > 1 else data["Close"]).dropna()
            if not series.empty:
                out[t] = series
        except KeyError:
            continue
    return out


def _return_since(series, rec_date: str) -> float | None:
    """추천일 이후 종가 기준 수익률. 추천일 데이터가 없으면 None."""
    after = series[series.index >= rec_date]
    if len(after) < 2:
        return None
    return float(after.iloc[-1]) / float(after.iloc[0]) - 1


def build_tracking_section(history_dir: str, today: str) -> tuple[str, str]:
    """(리포트용 마크다운, AI 프롬프트용 한 줄 요약) 반환."""
    entries = _load_history(history_dir, today)
    if not entries:
        md = ("## 지난 추천 성적표\n\n"
              "아직 검증할 추천 이력이 없습니다. 추천이 쌓이면 이 섹션에서 "
              "추천 이후 실제 수익률과 시장 대비 초과수익을 자동 집계합니다.\n")
        return md, ""

    earliest = min(e["date"] for e in entries)
    start = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    # 시세 수집: KR은 종목별 fdr, US는 벌크, 벤치마크는 시장별 1개
    us_tickers = sorted({c["ticker"] for e in entries for c in e["candidates"]
                         if c["market"] == "US"})
    us_prices = {}
    try:
        us_prices = _us_price_series(us_tickers, start)
    except Exception:
        pass
    bench = {}
    for market, symbol in BENCHMARKS.items():
        try:
            if market == "KR":
                bench[market] = _kr_price_series(symbol, start)
            else:
                bench[market] = _us_price_series([symbol], start).get(symbol)
        except Exception:
            bench[market] = None

    rows = []
    for e in entries:
        for c in e["candidates"]:
            row = {"date": e["date"], **c, "ret": None, "excess": None}
            try:
                if c["market"] == "KR":
                    series = _kr_price_series(c["ticker"], e["date"])
                else:
                    series = us_prices.get(c["ticker"])
                if series is not None:
                    row["ret"] = _return_since(series, e["date"])
            except Exception:
                pass
            b = bench.get(c["market"])
            if row["ret"] is not None and b is not None:
                bench_ret = _return_since(b, e["date"])
                if bench_ret is not None:
                    row["excess"] = row["ret"] - bench_ret
            rows.append(row)

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    evaluated = [
        r for r in rows
        if r["ret"] is not None
        and (today_dt - datetime.strptime(r["date"], "%Y-%m-%d")).days >= MIN_EVAL_DAYS
    ]

    lines = ["## 지난 추천 성적표\n"]
    summary = ""
    if evaluated:
        n = len(evaluated)
        avg_ret = sum(r["ret"] for r in evaluated) / n * 100
        win = sum(1 for r in evaluated if r["ret"] > 0) / n * 100
        with_excess = [r for r in evaluated if r["excess"] is not None]
        excess_txt = ""
        if with_excess:
            avg_excess = sum(r["excess"] for r in with_excess) / len(with_excess) * 100
            excess_txt = f", 시장(KOSPI·S&P500) 대비 평균 초과수익 {avg_excess:+.1f}%p"
        summary = (f"추천 후 {MIN_EVAL_DAYS}일 이상 경과한 {n}건 기준: "
                   f"평균 수익률 {avg_ret:+.1f}%, 승률 {win:.0f}%{excess_txt}")
        lines.append(summary + "\n")
    else:
        lines.append(f"추천 후 {MIN_EVAL_DAYS}일 이상 경과한 건이 아직 없어 "
                     "집계는 다음 주부터 제공됩니다. 최근 추천의 경과는 아래와 같습니다.\n")

    lines.append("| 추천일 | 종목 | 시장 | 추천가 | 수익률 | 시장 대비 |")
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x["date"], reverse=True)[:MAX_DETAIL_ROWS]:
        ret_txt = f"{r['ret'] * 100:+.1f}%" if r["ret"] is not None else "관찰 중"
        exc_txt = f"{r['excess'] * 100:+.1f}%p" if r["excess"] is not None else "-"
        lines.append(f"| {r['date']} | {r['name']} ({r['ticker']}) | {r['market']} "
                     f"| {r['price']:,} | {ret_txt} | {exc_txt} |")
    lines.append("")
    lines.append("_수익률은 추천일 이후 첫 거래일 종가에 매수했다고 가정한 종가 기준이며, "
                 "시장 대비는 같은 기간 시장 지수(KOSPI/S&P500) 수익률을 뺀 값입니다._\n")
    return "\n".join(lines), summary
