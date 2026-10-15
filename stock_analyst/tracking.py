"""고정 거래일 성과. 과거 퀀트 후보와 구조화 최종 추천을 분리한다."""
import argparse
from collections import Counter
from datetime import date as date_type, datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

import pandas as pd
from .quality import STRATEGY_VERSION, schedule
from .scoring import with_retry

HORIZONS = (5, 20, 60)
BENCHMARKS = {"US": "^GSPC", "KOSPI": "^KS11", "KOSDAQ": "^KQ11"}


def save_snapshot(history_dir, date, kr, us):
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    records = []
    for market, result in (("KR", kr), ("US", us)):
        for c in result.get("candidates", []):
            records.append({**c, "market": market, "ticker": str(c["ticker"])})
    data = {"schema_version": 2, "strategy_version": STRATEGY_VERSION,
            "run_id": run_id, "date": date, "generated_at": now.isoformat(),
            "available_at": None, "candidates": records,
            "markets": {"KR": {k: v for k, v in kr.items() if k != "candidates"},
                        "US": {k: v for k, v in us.items() if k != "candidates"}}}
    path = Path(history_dir) / "runs" / f"{date}-{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, allow_nan=False)
    return str(path)


def mark_published(path, available_at, url):
    stamp = pd.Timestamp(available_at)
    if stamp.tzinfo is None:
        raise ValueError("발행 시각에 시간대 필요")
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("available_at"):
        if data.get("published_at") == stamp.isoformat() and data.get("report_url") == url:
            return
        raise ValueError("이미 발행된 이력의 시각은 변경 불가")
    if stamp.floor("s") < pd.Timestamp(data["generated_at"]).floor("s"):
        raise ValueError("발행 시각이 생성 시각보다 빠름")
    # GitHub createdAt는 초 정밀도이므로 그 초의 끝 이후를 보수적 이용 가능 시각으로 사용.
    data.update(published_at=stamp.isoformat(), available_at=(stamp + pd.Timedelta(seconds=1)).isoformat(), report_url=url)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def load_history(history_dir, today):
    entries, errors = [], []
    paths = sorted(Path(history_dir).glob("????-??-??.json"))
    paths += sorted((Path(history_dir) / "runs").glob("*.json"))
    for p in paths:
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(e.get("candidates"), list) or not e.get("date"):
                raise ValueError("이력 형식 오류")
            date_type.fromisoformat(e["date"])
            if any(not isinstance(c, dict) or c.get("market") not in {"KR", "US"} or not c.get("ticker")
                   for c in e["candidates"]):
                raise ValueError("종목 이력 형식 오류")
            if e["date"] < today:
                entries.append(e)
        except Exception as err:
            errors.append({"file": p.name, "error": type(err).__name__})
    return entries, errors


def price_symbols(c):
    if c["market"] == "US":
        return c["ticker"], BENCHMARKS["US"]
    listing = c.get("listing_market")
    if listing not in {"KOSPI", "KOSDAQ"}:
        return None, None  # 과거 이력의 시장 구분을 추측하지 않는다.
    return c["ticker"] + (".KS" if listing == "KOSPI" else ".KQ"), BENCHMARKS[listing]


def download_prices(symbols, start, asof):
    """수정하지 않은 종가로 가격수익률 계산. 현금배당은 포함하지 않는다."""
    import yfinance as yf
    out, errors = {}, []
    end = (pd.Timestamp(asof).tz_convert("UTC").normalize() + pd.Timedelta(days=1)).date().isoformat()
    for i in range(0, len(symbols), 80):
        chunk = symbols[i:i+80]
        try:
            data = with_retry(yf.download, chunk, start=start, end=end, auto_adjust=False,
                              group_by="ticker", progress=False, threads=True, timeout=15)
            for symbol in chunk:
                try:
                    frame = data[symbol] if isinstance(data.columns, pd.MultiIndex) else data
                    close = frame["Close"].dropna()
                    if close.empty:
                        raise ValueError(f"빈 시세: {symbol}")
                    out[symbol] = close
                except (KeyError, ValueError, TypeError) as err:
                    errors.append({"symbols": [symbol], "error": str(err)[:200]})
        except Exception as err:
            errors.append({"symbols": chunk, "error": str(err)[:200]})
    return out, errors


def _series(series):
    if series is None:
        return None
    s = series.copy()
    if not isinstance(s, pd.Series):
        raise ValueError("종가가 1차원 Series가 아님")
    idx = pd.DatetimeIndex(s.index)
    s.index = idx.tz_localize(None).normalize()
    if s.index.duplicated().any():
        raise ValueError("중복 시세 날짜")
    return pd.to_numeric(s, errors="coerce").sort_index()


def evaluate(c, available_at, asof, prices, horizon, cost_bps=20):
    row = {"market": c["market"], "ticker": c["ticker"], "horizon": horizon,
           "status": "pending", "return": None, "excess": None, "net_return": None}
    if not available_at:
        return {**row, "status": "unknown_publication_time"}
    import math
    if not math.isfinite(cost_bps) or not 0 <= cost_bps < 20000:
        raise ValueError("왕복 비용은 0 이상 20000bp 미만이어야 함")
    if not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("보유 거래일은 양의 정수여야 함")
    sessions = schedule(c["market"], available_at)
    future = sessions[sessions["open"] > pd.Timestamp(available_at)]
    if len(future) <= horizon:
        return {**row, "status": "calendar_out_of_range"}
    entry, exit_ = future.index[0], future.index[horizon]
    row.update(entry_date=str(entry.date()), exit_date=str(exit_.date()))
    if future.iloc[horizon]["close"] > pd.Timestamp(asof):
        return row
    symbol, benchmark = price_symbols(c)
    if symbol is None:
        return {**row, "status": "unknown_listing_market"}
    try:
        s = _series(prices.get(symbol))
        try:
            b = _series(prices.get(benchmark))
        except (ValueError, TypeError):
            b = None
        if s is None or not all(d in s.index for d in (entry, exit_)):
            return {**row, "status": "missing_price"}
        entry_price, exit_price = float(s.loc[entry]), float(s.loc[exit_])
        from .quality import positive
        if not all(positive(v) for v in (entry_price, exit_price)):
            return {**row, "status": "invalid_price"}
        ret = exit_price / entry_price - 1
        row.update(status="ok", entry_price=entry_price, exit_price=exit_price,
                   return_=ret)
        row["return"] = row.pop("return_")
        row["net_return"] = (exit_price * (1-cost_bps/20000)) / (entry_price * (1+cost_bps/20000)) - 1
        # 같은 진입·청산일의 지수가 없으면 초과수익 계산 보류.
        if b is not None and all(d in b.index and positive(float(b.loc[d])) for d in (entry, exit_)):
            row["excess"] = ret - (float(b.loc[exit_]) / float(b.loc[entry]) - 1)
        else:
            row["benchmark_status"] = "missing_benchmark"
        return row
    except (ValueError, TypeError, KeyError) as err:
        return {**row, "status": "invalid_series", "error": str(err)}


def summarize(rows):
    ok = [r for r in rows if r["status"] == "ok"]
    excess = [r["excess"] for r in ok if r["excess"] is not None]
    values = [r["return"] for r in ok]
    return {"total": len(rows), "evaluated": len(ok), "excess_n": len(excess),
            "status_counts": dict(Counter(r["status"] for r in rows)),
            "mean_return": statistics.mean(values) if values else None,
            "median_return": statistics.median(values) if values else None,
            "win_rate": sum(v > 0 for v in values) / len(values) if values else None,
            "mean_net_return": statistics.mean(r["net_return"] for r in ok) if ok else None,
            "mean_excess": statistics.mean(excess) if excess else None}


def build_evaluation(entries, prices, asof, cost_bps=20):
    rows = []
    for e in entries:
        for c in e["candidates"]:
            for h in HORIZONS:
                try:
                    r = evaluate(c, e.get("available_at"), asof, prices, h, cost_bps)
                except (ValueError, TypeError, KeyError) as err:
                    r = {"market": c["market"], "ticker": c["ticker"], "horizon": h,
                         "status": "invalid_history", "return": None, "excess": None,
                         "net_return": None, "error": str(err)}
                r.update(date=e["date"], run_id=e.get("run_id", e["date"]),
                         legacy=e.get("schema_version") != 2, decision=c.get("decision", "unknown"))
                rows.append(r)
    groups = {}
    for cohort in ("quant", "final"):
        for market in ("KR", "US"):
            for h in HORIZONS:
                subset = [r for r in rows if r["horizon"] == h and r["market"] == market and
                          (cohort == "quant" or (not r["legacy"] and r["decision"] in {"pass", "conditional"}))]
                groups[f"{cohort}:{market}:{h}"] = summarize(subset)
    payload = {"strategy_version": STRATEGY_VERSION, "asof": asof,
               "cost_bps_round_trip": cost_bps, "groups": groups, "rows": rows}
    payload["evaluation_id"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return payload


def _pct(value, suffix="%"):
    return "미집계" if value is None else f"{value*100:+.2f}{suffix}"


def render_evaluation(result):
    lines = ["## 고정 거래일 성적표", "",
             f"집계 ID `{result['evaluation_id']}` / 기준 시각 {result['asof']} / 전략 {STRATEGY_VERSION}", "",
             "| 대상 | 시장 | 보유 거래일 | 전체/평가/초과수익 표본 | 평균 | 중앙값 | 승률 | 비용 차감 평균 | 초과수익 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, g in result["groups"].items():
        cohort, market, horizon = key.split(":")
        lines.append(f"| {'퀀트 후보' if cohort == 'quant' else '최종 추천'} | {market} | {horizon} | "
                     f"{g['total']}/{g['evaluated']}/{g['excess_n']} | {_pct(g['mean_return'])} | "
                     f"{_pct(g['median_return'])} | {_pct(g['win_rate'])} | {_pct(g['mean_net_return'])} | {_pct(g['mean_excess'], '%p')} |")
    lines += ["", "발행 후 시작하는 첫 거래일 종가 진입, 이후 5·20·60거래일 뒤 종가 청산. "
              "종목과 지수의 진입·청산일을 동일하게 고정한 현지통화 가격수익률(배당 제외)입니다. "
              f"왕복 비용 {result['cost_bps_round_trip']}bp는 예시 가정이며 벤치마크에는 차감하지 않습니다. "
              "반복 추천은 각각의 신호로 집계되므로 독립 표본이나 포트폴리오 수익률이 아닙니다.", "",
              "과거 이력은 발행 시각·최종 판정·한국 상장시장 구분이 없어 추정 복원하지 않습니다.", "",
              "| 대상 | 시장 | 거래일 | 상태별 건수 |", "|---|---|---|---|"]
    for key, g in result["groups"].items():
        cohort, market, h = key.split(":")
        lines.append(f"| {cohort} | {market} | {h} | {json.dumps(g['status_counts'], ensure_ascii=False)} |")
    return "\n".join(lines) + "\n"


def build_tracking_section(history_dir, today, asof=None):
    asof = asof or datetime.now(timezone.utc).isoformat()
    entries, errors = load_history(history_dir, today)
    symbols = sorted({s for e in entries if e.get("available_at") for c in e["candidates"]
                      for s in price_symbols(c) if s})
    start = min((e["date"] for e in entries), default=today)
    prices, fetch_errors = download_prices(symbols, start, asof) if symbols else ({}, [])
    result = build_evaluation(entries, prices, asof)
    result["history_errors"], result["fetch_errors"] = errors, fetch_errors
    result["data_source"] = "yfinance Close auto_adjust=False; 현금배당 제외"
    result["history_sha256"] = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    target = Path(history_dir).parent / "evaluations" / f"{today}-{result['evaluation_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    price_rows = [{"date": str(pd.Timestamp(d).date()), "symbol": symbol, "close": float(v)}
                  for symbol, series in sorted(prices.items()) for d, v in series.items()]
    price_path = target.with_name(target.stem + "-prices.csv")
    pd.DataFrame(price_rows, columns=["date", "symbol", "close"]).to_csv(price_path, index=False)
    result["price_file_sha256"] = hashlib.sha256(price_path.read_bytes()).hexdigest()
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    md = render_evaluation(result)
    if errors or fetch_errors:
        md += f"\n수집/이력 오류: {len(errors)} / {len(fetch_errors)}건. 상세는 집계 JSON 참조.\n"
    # AI에 숫자를 재서술시키지 않는다.
    return md, ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-published", required=True)
    parser.add_argument("--available-at", required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    mark_published(args.mark_published, args.available_at, args.url)
