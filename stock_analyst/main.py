"""오케스트레이션 + CLI.

사용법:
    python -m stock_analyst.main [--dry-run] [--market kr|us|all] [--out-dir reports]

한 시장의 수집 실패가 전체 실행을 죽이지 않도록 시장별로 격리하고,
리포트를 reports/runs/에 실행별로 저장한 뒤 GitHub Actions 출력 변수
(report_path, report_title, report_date)를 내보낸다.
"""

import argparse
import os
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .report import build_report
from .quality import apply_gates, utc_now

KST = timezone(timedelta(hours=9))


def _run_market(label: str, screen_fn) -> dict:
    try:
        result = screen_fn()
        print(f"[info] {label}: {result['scanned']:,}개 스캔, "
              f"후보 {len(result['candidates'])}개 (기준일 {result['date']})")
        return result
    except Exception as err:
        traceback.print_exc()
        return {"collection_error": f"{type(err).__name__}: {str(err)[:300]}", "date": "-", "candidates": [], "scanned": 0,
                "note": f"{label} 데이터 수집 실패 — 소스 오류"}


def main() -> None:
    parser = argparse.ArgumentParser(description="일일 주식 스크리닝 + 분석 리포트")
    parser.add_argument("--dry-run", action="store_true",
                        help="Claude API 호출 없이 퀀트 리포트만 생성")
    parser.add_argument("--market", choices=["kr", "us", "all"], default="all")
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    empty = {"date": "-", "candidates": [], "scanned": 0, "note": "이번 실행에서 제외"}
    kr = {**empty, "candidates": []}
    us = {**empty, "candidates": []}
    if args.market in ("kr", "all"):
        from . import kr_screener
        kr = _run_market("한국", kr_screener.screen)
    if args.market in ("us", "all"):
        from . import us_screener
        us = _run_market("미국", us_screener.screen)

    report_date = datetime.now(KST).strftime("%Y-%m-%d")

    # 사전 검증: 목표주가 컨센서스·최근 뉴스를 후보에 덧붙임(실패해도 계속)
    try:
        from . import verify
        verify.enrich(kr, us)
    except Exception:
        traceback.print_exc()

    # 성과 검증: 과거 추천의 실제 수익률 집계(실패해도 리포트는 계속)
    history_dir = str(Path(args.out_dir) / "history")
    tracking_md, track_summary = "", ""
    try:
        from . import tracking
        tracking_md, track_summary = tracking.build_tracking_section(history_dir, report_date)
        if track_summary:
            print(f"[info] 성과 집계: {track_summary}")
    except Exception:
        traceback.print_exc()

    if not tracking_md:
        tracking_md = "## 고정 거래일 성적표\n\n성과 집계 실패 — 성과 수치를 표시하지 않습니다.\n"

    apply_gates(kr, us, utc_now())

    markdown = build_report(kr, us, report_date, dry_run=args.dry_run,
                            tracking_md=tracking_md, track_summary=track_summary)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now(KST).strftime("%H%M%S%f")
    out_path = out_dir / "runs" / f"{report_date}-{run_stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"[info] 리포트 저장: {out_path}")

    # 이력 저장 실패 시 게시하지 않는다. 성적표 없는 추천 이력을 만들지 않음.
    from . import tracking
    snapshot_path = tracking.save_snapshot(history_dir, report_date, kr, us)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"report_path={out_path}\n")
            fh.write(f"report_title=주식 분석 리포트 {report_date}\n")
            fh.write(f"report_date={report_date}\n")
            fh.write(f"snapshot_path={snapshot_path}\n")


if __name__ == "__main__":
    main()
