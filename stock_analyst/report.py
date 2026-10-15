"""리포트 생성: 퀀트 결과를 마크다운으로 조립하고, Claude가 전문가 패널 토론 형식의
분석을 덧붙인다. API 키가 없거나 호출이 실패하면 퀀트-only 리포트로 폴백한다."""

import json
import os

from . import config

DISCLAIMER = (
    "## 면책 조항\n\n"
    "이 리포트는 공개 데이터 기반의 자동 퀀트 스크리닝과 AI 분석 결과이며, "
    "투자 자문이 아닙니다. 재무 데이터에는 오류나 지연이 있을 수 있고, "
    "과거 지표가 미래 수익을 보장하지 않습니다. 투자 판단과 손익의 책임은 "
    "투자자 본인에게 있습니다.\n"
)

SYSTEM_PROMPT = """당신은 공개 데이터 기반 투자 후보 검토 AI다. 실제 전문가 패널이 아니다.
가치·모멘텀·리스크·매크로·산업의 서로 다른 관점으로 반박하고 근거가 있는 판단만 제시하라.
제공되지 않은 최신 실적·뉴스·매크로·표결·상승확률을 만들지 마라.
목표주가보다 현재가가 높다는 이유만으로 고평가·가치 함정을 확정하지 마라.
목표가 작성일 미상, 공시·실적 일정 미검증 등 한계를 근거에 포함하라.
gate_status가 eligible이 아니면 pass/conditional을 제안하지 마라. 코드의 품질 게이트를 우회할 수 없다.
확신도는 투자 상승확률이 아니며 독립 검증 전에는 상을 주지 마라.
응답은 다음 형식의 JSON 객체만 출력하라. 모든 후보를 정확히 한 번 포함하라.
{"decisions": [{"market": "US 또는 KR", "ticker": "티커", "decision": "pass 또는 conditional 또는 reject",
"confidence": "중 또는 하", "reason": "한국어로 검토 근거·상충 논점·남은 위험"}]}
성과 수치와 추천 표는 코드에서 생성하므로 응답에 쓰지 마라."""


def _fmt_table(candidates: list[dict], is_kr: bool) -> str:
    if not candidates:
        return "_후보 없음_\n"
    cap_key = "market_cap_krw_bn" if is_kr else "market_cap_usd_bn"
    cap_label = "시총(십억원)" if is_kr else "시총($B)"
    lines = [
        f"| 순위 | 종목 | 종가 | PER | PBR | ROE% | 배당% | {cap_label} "
        "| 52주위치 | 60일% | 목표가여력 | V | M | 종합 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(candidates, 1):
        upside = c.get("target_upside_pct")
        upside_txt = f"{upside:+.0f}%" if upside is not None else "-"
        lines.append(
            f"| {i} | {c['name']} ({c['ticker']}) | {c['price']:,} | {c['per']} "
            f"| {c['pbr']} | {c['roe_pct']} | {c['div_pct']} | {c[cap_key]:,} "
            f"| {c['week52_position']} | {c['return_60d_pct']} | {upside_txt} "
            f"| {c['value_score']} | {c['momentum_score']} | {c['composite_score']} |"
        )
    return "\n".join(lines) + "\n"


def _methodology(kr: dict, us: dict) -> str:
    return (
        "## 스캔 범위 및 방법론\n\n"
        f"- 한국: KOSPI+KOSDAQ 목록 {kr.get('scanned', 0):,}개 수집 "
        f"(기준일 {kr.get('date', '-')}). 시총 3,000억원·거래대금 10억원 이상, "
        "흑자 기업만 대상.\n"
        f"- 미국: {us.get('universe_label', 'S&P500+NASDAQ-100 수집 시도')} 목록 {us.get('scanned', 0):,}개 "
        f"(기준일 {us.get('date', '-')}). 소형주는 무료 데이터 한계로 제외 — "
        "실제 시세·재무 수집 성공 건수는 수집 진단 참조.\n"
        "- 점수: 가치(PER·PBR·ROE·배당 백분위) 60% + 모멘텀(52주 위치·이동평균·"
        "60일 수익률·거래량 백분위) 40%. ROE 5% 미만은 밸류트랩 방지를 위해 제외.\n"
    )


def build_quant_section(kr: dict, us: dict) -> str:
    parts = ["## 퀀트 스크리닝 결과\n"]
    parts.append(f"### 한국 (기준일 {kr.get('date', '-')})\n")
    if kr.get("note"):
        parts.append(f"> {kr['note']}\n")
    parts.append(_fmt_table(kr.get("candidates", []), is_kr=True))
    parts.append(f"\n### 미국 (기준일 {us.get('date', '-')})\n")
    if us.get("note"):
        parts.append(f"> {us['note']}\n")
    parts.append(_fmt_table(us.get("candidates", []), is_kr=False))
    return "\n".join(parts)


def _user_prompt(kr: dict, us: dict, track_summary: str = "") -> str:
    payload = {
        "korea": {"data_date": kr.get("date"), "note": kr.get("note"),
                  "candidates": kr.get("candidates", [])},
        "us": {"data_date": us.get("date"), "note": us.get("note"),
               "candidates": us.get("candidates", [])},
    }
    return "후보 데이터를 검토하고 지정한 JSON 형식으로 응답하세요.\n" + json.dumps(payload, ensure_ascii=False)


def gemini_analysis(kr: dict, us: dict, api_key: str, track_summary: str = "") -> str:
    """Gemini(무료 티어) 전문가 패널 분석."""
    import requests

    resp = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": api_key},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user",
                          "parts": [{"text": _user_prompt(kr, us, track_summary)}]}],
            "generationConfig": {"maxOutputTokens": config.GEMINI_MAX_TOKENS,
                                 "responseMimeType": "application/json"},
        },
        timeout=300,
    )
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise ValueError("Gemini 응답이 비어 있음(안전 필터 또는 토큰 한도)")
    return text


def claude_analysis(kr: dict, us: dict, api_key: str, track_summary: str = "") -> str:
    """Claude 전문가 패널 분석."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CLAUDE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(kr, us, track_summary)}],
    )
    return "".join(b.text for b in message.content if b.type == "text")


def ai_analysis(kr: dict, us: dict, track_summary: str = "") -> str | None:
    """가용한 키 순서(Gemini → Claude)로 분석 시도. 모두 실패하면 None."""
    providers = []
    if os.environ.get("GEMINI_API_KEY"):
        providers.append(("Gemini", gemini_analysis, os.environ["GEMINI_API_KEY"]))
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append(("Claude", claude_analysis, os.environ["ANTHROPIC_API_KEY"]))
    for name, fn, key in providers:
        try:
            return fn(kr, us, key, track_summary)
        except Exception as err:  # noqa: BLE001 - 리포트 자체는 실패시키지 않는다
            print(f"[warn] {name} 분석 실패: {err}")
    return None


def build_report(kr: dict, us: dict, report_date: str, dry_run: bool,
                 tracking_md: str = "", track_summary: str = "") -> str:
    parts = [f"# 일일 주식 분석 리포트 — {report_date}\n"]
    analysis = None if dry_run else ai_analysis(kr, us, track_summary)
    if dry_run:
        parts.append("> [DRY RUN] AI 분석 없이 퀀트 스크리닝 결과만 포함된 리포트입니다.\n")
    elif analysis is None:
        parts.append("> AI 분석을 사용할 수 없어 퀀트 스크리닝 결과만 포함합니다. "
                     "(GEMINI_API_KEY/ANTHROPIC_API_KEY 미설정 또는 API 오류)\n")
    from .quality import apply_decisions
    if analysis:
        try:
            raw = analysis.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.splitlines()[1:-1])
            decisions = json.loads(raw)["decisions"]
            expected = sum(len(r.get("candidates", [])) for r in (kr, us))
            if len(decisions) != expected:
                raise ValueError("후보 판정 누락")
            apply_decisions(kr, us, decisions)
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            parts.append(f"> AI 구조화 판정 검증 실패({type(err).__name__}) — 최종 추천 보류.\n")
    parts.append(build_decision_section(kr, us))
    if tracking_md:
        parts.append(tracking_md)
    parts.append(build_quant_section(kr, us))
    parts.append(_methodology(kr, us))
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def build_decision_section(kr, us):
    labels = {"pass": "통과", "conditional": "조건부 통과", "reject": "탈락", "observe": "관찰·추천 보류"}
    parts = ["## 데이터 수집 상태", "",
             "| 시장 | 상태 | 직전 완료 거래일 | 수집 진단 |", "|---|---|---|---|"]
    for m, r in (("KR", kr), ("US", us)):
        parts.append(f"| {m} | {r.get('status', 'unknown')} | {r.get('expected_session', '-')} | "
                     f"{json.dumps(r.get('quality', {}), ensure_ascii=False)} |")
        if r.get("collection_error"):
            parts.append(f"\n> {m} 수집 오류: {r['collection_error']}\n")
    parts += ["", "## 검증 결과 및 최종 추천", "",
              "AI 분석은 단일 모델의 관점별 검토이며 실제 전문가 투표가 아닙니다. "
              "시세·뉴스 게이트 통과는 안전성 보증이 아닙니다. 공시·실적 일정은 별도 미검증 상태이며 확신도 상을 부여하지 않습니다.", "",
              "| 시장 | 종목 | 판정 | 확신도 | 모의 비중 상한 | 시세일 | 뉴스 상태 | 보류 사유 |",
              "|---|---|---|---|---|---|---|---|"]
    analyses = []
    for m, r in (("KR", kr), ("US", us)):
        for c in r.get("candidates", []):
            reasons = "; ".join(c.get("gate_reasons", [])) or "-"
            parts.append(f"| {m} | {c['name']} ({c['ticker']}) | {labels.get(c.get('decision'), '관찰')} | "
                         f"{c.get('confidence', '하')} | {c.get('allocation_pct', 0):g}% | "
                         f"{c.get('price_date', '-')} | {c.get('news_status', 'unknown')} | {reasons} |")
            if c.get("analysis"):
                # AI 텍스트는 표/제목으로 해석하지 않고 인용문으로만 표시한다.
                reason = c["analysis"].replace("\n", " ").replace("|", "/")
                analyses.append(f"> {c['ticker']} AI 검토: {reason}\n")
    parts += [""] + analyses
    parts += ["", "모의 비중은 종목당 최대 10%, 업종당 최대 25%, 최대 5종목이며 잔여분은 현금입니다. "
              "이는 미검증 초기 제한값이며 실제 주문·보유 포트폴리오가 아닙니다. 한국 데이터 실패분을 미국에 추가 배분하지 않습니다.", ""]
    return "\n".join(parts)
