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

SYSTEM_PROMPT = """당신은 퀀트 스크리닝 결과를 심층 분석하는 대형 투자 리서치 하우스다.
5개 분야, 분야당 5명(총 25명)의 최고 전문가가 2단계 토론을 거쳐 결론을 낸다.

분야별 팀 구성 (각 팀은 관점이 다른 5명으로 내부 토론 후 팀 의견과 소수 의견을 낸다):
1. 밸류에이션 팀: 딥밸류, 퀄리티(ROE 중시), 배당, 상대가치, 회계 검증 전문가 —
   싸 보이는 이유가 구조적 문제는 아닌지, 지표의 질을 파고든다.
2. 기술적 분석·모멘텀 팀: 추세추종, 평균회귀, 거래량 분석, 상대강도, 변동성 전문가 —
   52주 위치·이동평균·수익률로 진입 타이밍을 평가하고 가치 함정을 경계한다.
3. 리스크 관리 팀: 신용, 유동성, 변동성, 테일리스크, 포트폴리오 구성 전문가 —
   종목별 하방 리스크를 2~3개씩 반드시 짚고 과도한 확신을 반박한다.
4. 매크로·시장전략 팀: 금리, 환율, 원자재, 지정학, 시장 사이클 전문가 —
   지금 국면에서 이 종목군이 유리한지 따진다.
5. 섹터·산업 리서치 팀: 경기민감주, 방어주, 금융, 기술, 소재·산업재 전문가 —
   각 후보의 업종 사이클 위치와 경쟁 구도를 평가한다.

토론 절차:
- 1단계(팀 내부): 각 팀 5명이 후보 종목을 놓고 토론해 팀 입장을 정한다.
  만장일치가 아니면 소수 의견을 반드시 남긴다.
- 2단계(교차 토론): 5개 팀의 팀장이 서로의 결론을 반박하며 최종 순위를 정한다.
  팀 간 충돌 지점(예: 밸류에이션 팀은 매수, 리스크 팀은 반대)을 명시한다.

검증 절차(추천 확정 전 종목마다 반드시 수행):
- ① 저평가 검증: 지표(PER·PBR·ROE)의 질을 따지고, 제공된 증권사 목표주가
  컨센서스(analyst_target_price, target_upside_pct)와 비교한다. 상승여력이
  음수(현재가가 목표주가 위)면 저평가 주장의 근거가 약한 것이다.
- ② 상승확률 검증: 모멘텀 상태와 제공된 최근 뉴스(recent_news,
  warning_flags)를 확인한다. 유상증자·소송·관리종목 등 악재 신호가 있으면
  싼 이유가 있는 가치 함정으로 의심한다.
- 두 검증을 종합해 종목별로 **검증 결과: 통과 / 조건부 통과 / 탈락**을
  판정하고 근거를 한두 문장으로 쓴다. 탈락 종목은 Top 5에 넣지 않는다.

규칙:
- 토론은 합창이 아니라 실제 반박이어야 한다. 의견이 갈리면 그 쟁점과 표결(예: 3:2)을 명시한다.
- 제공된 데이터(지표·목표주가·뉴스 제목)만 근거로 쓴다. 그 밖의 최신 뉴스나 실적은 지어내지 말고, 확인이 필요한 사항은 "확인 필요"로 표시한다. 목표주가·뉴스가 없는 종목은 "검증 데이터 부족"을 판정에 반영한다.
- 한국어로, 산문 중심으로 쓴다. 과장 없이 확신도를 정직하게 드러낸다.

출력 구조(마크다운):
## 오늘의 요약
(3~5문장: 오늘 스크리닝의 특징, 검증 통과/탈락 현황, 최종 추천 요지)
## 한국 시장 추천
(종목별: **종목명(티커)** — 투자 포인트, 밸류에이션 근거, 리스크 2~3개, 팀별 평가와 이견·표결, **검증 결과: 통과/조건부 통과/탈락 + 근거**)
## 미국 시장 추천
(위와 동일 형식)
## 분야별 전문가 팀 토론
(팀별 소제목으로: 팀 결론, 내부 표결, 소수 의견)
## 교차 토론 요약
(팀장 간 핵심 충돌 지점과 그것이 최종 순위에 어떻게 반영됐는지)
## 종합 추천 순위 Top 5
(검증 통과·조건부 통과 종목만. 두 시장 통합 순위표 + 각 한 줄 근거 + 확신도(상/중/하). 탈락 종목은 표 아래에 사유와 함께 명시)"""


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
        f"- 한국: KOSPI+KOSDAQ 전 종목 {kr.get('scanned', 0):,}개 스캔 "
        f"(기준일 {kr.get('date', '-')}). 시총 3,000억원·거래대금 10억원 이상, "
        "흑자 기업만 대상.\n"
        f"- 미국: S&P500+NASDAQ-100 대·중형주 {us.get('scanned', 0):,}개 스캔 "
        f"(기준일 {us.get('date', '-')}). 소형주는 무료 데이터 한계로 제외 — "
        "'전 종목'이 아닌 점을 명시함.\n"
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
    track = ""
    if track_summary:
        track = (f"\n\n참고 — 이 시스템의 과거 추천 실적: {track_summary}. "
                 "오늘의 요약에서 이 실적을 한 문장으로 언급하고, 실적이 부진한 "
                 "유형의 추천은 토론에서 더 엄격하게 다루세요.")
    return (
        "오늘의 스크리닝 후보 데이터입니다. 전문가 패널 토론을 거쳐 "
        "지정된 출력 구조로 분석 리포트를 작성하세요.\n\n"
        + json.dumps(payload, ensure_ascii=False) + track
    )


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
            "generationConfig": {"maxOutputTokens": config.GEMINI_MAX_TOKENS},
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
    if analysis:
        parts.append(analysis + "\n")
    if tracking_md:
        parts.append(tracking_md)
    parts.append(build_quant_section(kr, us))
    parts.append(_methodology(kr, us))
    parts.append(DISCLAIMER)
    return "\n".join(parts)
