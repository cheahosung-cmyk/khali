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

SYSTEM_PROMPT = """당신은 퀀트 스크리닝 결과를 심층 분석하는 투자 리서치 팀이다.
아래 4명의 최고 전문가가 실제로 충돌하는 토론을 거쳐 결론을 낸다:

- 가치투자 애널리스트: 밸류에이션(PER·PBR·ROE·배당)의 질을 파고들고, 싸 보이는 이유가 구조적 문제는 아닌지 의심한다.
- 모멘텀 트레이더: 추세·수급·52주 위치를 근거로 진입 타이밍을 평가하고, 가치 함정을 경계한다.
- 리스크 매니저: 각 종목의 하방 리스크(업황·재무·유동성)를 2~3개씩 반드시 짚고, 과도한 확신을 반박한다.
- 매크로 전략가: 금리·환율·섹터 사이클 관점에서 지금 이 종목군이 유리한지 따진다.

규칙:
- 토론은 합창이 아니라 실제 반박이어야 한다. 전문가끼리 의견이 갈리면 그 쟁점을 명시한다.
- 제공된 지표 데이터만 근거로 쓴다. 모르는 최신 뉴스나 실적은 지어내지 말고, 확인이 필요한 사항은 "확인 필요"로 표시한다.
- 한국어로, 산문 중심으로 쓴다. 과장 없이 확신도를 정직하게 드러낸다.

출력 구조(마크다운):
## 오늘의 요약
(3~5문장: 오늘 스크리닝의 특징과 최종 추천 요지)
## 한국 시장 추천
(종목별: **종목명(티커)** — 투자 포인트, 밸류에이션 근거, 리스크 2~3개, 전문가 이견이 있으면 명시)
## 미국 시장 추천
(위와 동일 형식)
## 전문가 토론 요약
(4인의 핵심 충돌 지점과 그것이 어떻게 최종 순위에 반영됐는지)
## 종합 추천 순위 Top 5
(두 시장 통합 순위표 + 각 한 줄 근거)"""


def _fmt_table(candidates: list[dict], is_kr: bool) -> str:
    if not candidates:
        return "_후보 없음_\n"
    cap_key = "market_cap_krw_bn" if is_kr else "market_cap_usd_bn"
    cap_label = "시총(십억원)" if is_kr else "시총($B)"
    lines = [
        f"| 순위 | 종목 | 종가 | PER | PBR | ROE% | 배당% | {cap_label} | 52주위치 | 60일% | V | M | 종합 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"| {i} | {c['name']} ({c['ticker']}) | {c['price']:,} | {c['per']} "
            f"| {c['pbr']} | {c['roe_pct']} | {c['div_pct']} | {c[cap_key]:,} "
            f"| {c['week52_position']} | {c['return_60d_pct']} "
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


def claude_analysis(kr: dict, us: dict) -> str | None:
    """Claude 전문가 패널 분석. 키가 없거나 실패하면 None."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic

        payload = {
            "korea": {"data_date": kr.get("date"), "note": kr.get("note"),
                      "candidates": kr.get("candidates", [])},
            "us": {"data_date": us.get("date"), "note": us.get("note"),
                   "candidates": us.get("candidates", [])},
        }
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "오늘의 스크리닝 후보 데이터입니다. 전문가 패널 토론을 거쳐 "
                    "지정된 출력 구조로 분석 리포트를 작성하세요.\n\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            }],
        )
        return "".join(b.text for b in message.content if b.type == "text")
    except Exception as err:  # noqa: BLE001 - 리포트 자체는 실패시키지 않는다
        print(f"[warn] Claude 분석 실패, 퀀트-only 리포트로 폴백: {err}")
        return None


def build_report(kr: dict, us: dict, report_date: str, dry_run: bool) -> str:
    parts = [f"# 일일 주식 분석 리포트 — {report_date}\n"]
    analysis = None if dry_run else claude_analysis(kr, us)
    if dry_run:
        parts.append("> [DRY RUN] Claude 분석 없이 퀀트 스크리닝 결과만 포함된 리포트입니다.\n")
    elif analysis is None:
        parts.append("> Claude 분석을 사용할 수 없어 퀀트 스크리닝 결과만 포함합니다. "
                     "(ANTHROPIC_API_KEY 미설정 또는 API 오류)\n")
    if analysis:
        parts.append(analysis + "\n")
    parts.append(build_quant_section(kr, us))
    parts.append(_methodology(kr, us))
    parts.append(DISCLAIMER)
    return "\n".join(parts)
