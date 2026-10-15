"""동결한 이력·시세 CSV의 재현 가능한 신호 백테스트. 네트워크 호출 없음.

python -m stock_analyst.backtest --history reports/history --prices prices.csv \
  --asof 2026-10-15T22:10:00Z --output reports/audits/backtest.json
CSV: date,symbol,close (벤치마크도 같은 형식으로 포함).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd
from .tracking import build_evaluation, load_history, summarize


def without_overlap(rows):
    """동일 시장·종목·기간의 보유 중 반복 신호 제외. 포트폴리오 성과가 아니다."""
    accepted, held_until = [], {}
    for r in sorted(rows, key=lambda x: (x.get("entry_date", "9999"), x["date"], x["run_id"])):
        if r["status"] != "ok":
            accepted.append(r)
            continue
        key = (r["market"], r["ticker"], r["horizon"])
        if key in held_until and r["entry_date"] <= held_until[key]:
            accepted.append({**r, "status": "overlap_excluded", "return": None,
                             "net_return": None, "excess": None})
        else:
            held_until[key] = r["exit_date"]
            accepted.append(r)
    return accepted


def run(history_dir, prices_path, asof):
    stamp = pd.Timestamp(asof)
    if stamp.tzinfo is None:
        raise ValueError("기준 시각 시간대 필요")
    frame = pd.read_csv(prices_path)
    if not {"date", "symbol", "close"}.issubset(frame):
        raise ValueError("CSV 필수 컬럼: date,symbol,close")
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("중복 가격 행")
    frame["date"] = pd.to_datetime(frame["date"])
    prices = {symbol: g.set_index("date")["close"] for symbol, g in frame.groupby("symbol")}
    # 미래 날짜의 이력도 evaluate에서 발행·청산 시각을 검사한다.
    entries, errors = load_history(history_dir, (stamp.tz_convert("Asia/Seoul") + pd.Timedelta(days=1)).date().isoformat())
    scenarios = {}
    for cost in (0, 20, 50):
        result = build_evaluation(entries, prices, asof, cost)
        groups = {}
        for cohort in ("quant", "final"):
            for market in ("KR", "US"):
                for horizon in (5,20,60):
                    rows = [r for r in result["rows"] if r["market"]==market and r["horizon"]==horizon
                            and (cohort=="quant" or (not r["legacy"] and r["decision"] in {"pass","conditional"}))]
                    groups[f"{cohort}:{market}:{horizon}"] = summarize(without_overlap(rows))
        scenarios[str(cost)] = {"all_signals":result["groups"], "no_overlap":groups}
    return {"asof":asof, "price_file_sha256":hashlib.sha256(Path(prices_path).read_bytes()).hexdigest(),
            "history_errors":errors,
            "history_sha256":hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest(),
            "scenarios_round_trip_bps":scenarios,
            "limitations":["신호별 성과이며 포트폴리오 수익률·최대낙폭이 아님", "발행 시각 미상 과거 이력은 성과 미집계",
                            "당시 재무·뉴스·상장폐지 시세가 없으면 점수 변경·뉴스 필터의 과거 효과 검증 불가",
                            "배당·환율 미포함 가격수익률, 분할 등 기업행위는 입력 시세에서 검증 필요"]}


def audit(history_dir):
    entries, errors=load_history(history_dir,'9999-12-31')
    records=[c for e in entries for c in e['candidates']]
    counts=Counter((c['market'],c['ticker']) for c in records)
    return {"snapshot_count":len(entries), "candidate_events":len(records),
            "unique_market_tickers":len(counts),
            "repeat_events_after_first":sum(n-1 for n in counts.values()),
            "unknown_publication_snapshots":sum(not e.get('available_at') for e in entries),
            "unknown_final_decision_events":sum('decision' not in c for c in records),
            "history_errors":errors,
            "meaning":"반복 신호는 독립 거래가 아니며, 발행 시각·최종 판정 미상은 추측하지 않음"}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--history',default='reports/history')
    p.add_argument('--prices')
    p.add_argument('--asof')
    p.add_argument('--audit',action='store_true')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    if not a.audit and (not a.prices or not a.asof):
        p.error('--prices 및 --asof 필요')
    result=audit(a.history) if a.audit else run(a.history,a.prices,a.asof)
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(result if a.audit else {"output":str(target),"scenarios":3},ensure_ascii=False))
