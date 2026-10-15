"""시장 달력과 데이터 품질 게이트. AI 판단보다 먼저 적용한다."""
from datetime import datetime, timezone
import math
from functools import lru_cache

import pandas as pd
import exchange_calendars as xc

STRATEGY_VERSION = "quality-v2"
CALENDARS = {"KR": "XKRX", "US": "XNYS"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=16)
def calendar(market, year):
    return xc.get_calendar(CALENDARS[market], start=f"{year-1}-01-01", end=f"{year+2}-12-31")


def schedule(market, at):
    stamp = pd.Timestamp(at)
    if stamp.tzinfo is None:
        raise ValueError("시간대가 있는 기준 시각 필요")
    return calendar(market, stamp.year).schedule


def last_completed_session(market, at):
    s = schedule(market, at)
    completed = s[s["close"] <= pd.Timestamp(at)]
    if completed.empty:
        raise ValueError("완료 거래일 없음")
    return str(completed.index[-1].date())


def positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def apply_gates(kr, us, at=None):
    at = at or utc_now()
    for market, result in (("KR", kr), ("US", us)):
        result["collected_at"] = at
        try:
            expected = last_completed_session(market, at)
            result["expected_session"] = expected
        except Exception as err:
            expected = None
            result["calendar_error"] = str(err)
        quality = result.setdefault("quality", {})
        ratios = [v for k, v in quality.items() if k.endswith("_coverage")]
        valid_ratios = all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in ratios)
        failed = result.get("note") != "이번 실행에서 제외" and (
            result.get("scanned", 0) == 0 or bool(result.get("collection_error")) or "실패" in result.get("note", ""))
        blocked = failed or not ratios or not valid_ratios or min(ratios) < 0.90 or expected is None
        result["status"] = ("excluded" if result.get("note") == "이번 실행에서 제외" else
                            "failed" if failed else "partial" if blocked or min(ratios) < 0.95 else
                            "no_candidates" if not result.get("candidates") else "ok")
        result["recommendations_blocked"] = blocked
        for c in result.get("candidates", []):
            reasons = []
            if blocked:
                reasons.append("시장 수집률 미달 또는 수집 상태 확인 불가")
            if c.get("price_date") != expected:
                reasons.append("직전 완료 거래일 시세 미확인")
            if not all(positive(c.get(k)) for k in ("price", "per", "pbr", "roe_pct")):
                reasons.append("핵심 가격·재무 데이터 오류")
            div = c.get("div_pct")
            if not isinstance(div, (int, float)) or not math.isfinite(div) or div < 0:
                reasons.append("배당 데이터 미확인")
            if c.get("news_status") != "ok":
                reasons.append("최근 뉴스 조회 실패·기간 확인 불가 또는 기사 없음")
            if c.get("warning_flags"):
                reasons.append("악재 의심 신호 추가 확인 필요")
            if c.get("fundamental_asof") is None:
                reasons.append("재무 기준일 미확인")
            if not c.get("sector"):
                reasons.append("업종 미확인")
            c["gate_reasons"] = reasons
            c["gate_status"] = "observe" if reasons else "eligible"
            c["decision"] = "observe"
            c["confidence"] = "하"
            c["allocation_pct"] = 0.0


def apply_decisions(kr, us, decisions):
    """구조화 AI 판정을 품질 게이트 아래에 적용. 비중은 모의운용 상한이다."""
    all_candidates = {(m, str(c["ticker"])): c for m, r in (("KR", kr), ("US", us))
                      for c in r.get("candidates", [])}
    if not isinstance(decisions, list) or not all(isinstance(d, dict) for d in decisions):
        raise ValueError("AI 판정은 객체 목록이어야 함")
    seen = set()
    for d in decisions:
        key = (d.get("market"), str(d.get("ticker")))
        if key not in all_candidates or key in seen:
            raise ValueError("알 수 없거나 중복된 AI 종목 판정")
        seen.add(key)
        if d.get("decision") not in {"pass", "conditional", "reject"}:
            raise ValueError("잘못된 AI 판정")
        if d.get("confidence") not in {"상", "중", "하"}:
            raise ValueError("잘못된 확신도")
    if seen != set(all_candidates):
        raise ValueError("AI 후보 판정 누락")
    # 먼저 전체 응답을 검증한 뒤 변경한다.
    for d in decisions:
        c = all_candidates[(d["market"], str(d["ticker"]))]
        c["ai_decision"] = d["decision"]
        c["analysis"] = str(d.get("reason", ""))[:2000]
        if c["gate_status"] == "eligible":
            c["decision"] = d["decision"]
            # 뉴스만으로 공시·재무·이벤트 위험 전체를 확인한 것은 아니다.
            c["confidence"] = "중" if d["confidence"] == "상" else d["confidence"]
    sectors = {}
    selected = sorted((c for c in all_candidates.values() if c["decision"] in {"pass", "conditional"}),
                      key=lambda c: c.get("composite_score", 0), reverse=True)
    for i, c in enumerate(selected):
        sector = c["sector"]
        weight = min(10.0, 25.0 - sectors.get(sector, 0)) if i < 5 else 0
        if weight <= 0:
            c["decision"] = "observe"
            c["gate_reasons"].append("Top 5 또는 업종 비중 상한")
            continue
        c["allocation_pct"] = weight
        sectors[sector] = sectors.get(sector, 0) + weight
