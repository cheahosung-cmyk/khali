"""오케스트레이션 + CLI.

사용법:
    python -m stock_analyst.main [--dry-run] [--market kr|us|all] [--out-dir reports]

한 시장의 수집 실패가 전체 실행을 죽이지 않도록 시장별로 격리하고,
리포트를 reports/YYYY-MM-DD.md로 저장한 뒤 GitHub Actions 출력 변수
(report_path, report_title, report_date)를 내보낸다.
"""

import argparse
import os
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .report import build_report

KST = timezone(timedelta(hours=9))


def _run_market(label: str, screen_fn) -> dict:
    try:
        result = screen_fn()
        print(f"[info] {label}: {result['scanned']:,}개 스캔, "
              f"후보 {len(result['candidates'])}개 (기준일 {result['date']})")
        return result
    except Exception:
        traceback.print_exc()
        return {"date": "-", "candidates": [], "scanned": 0,
                "note": f"{label} 데이터 수집 실패 — 소스 오류"}


def main() -> None:
    parser = argparse.ArgumentParser(description="일일 주식 스크리닝 + 분석 리포트")
    parser.add_argument("--dry-run", action="store_true",
                        help="Claude API 호출 없이 퀀트 리포트만 생성")
    parser.add_argument("--market", choices=["kr", "us", "all"], default="all")
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    empty = {"date": "-", "candidates": [], "scanned": 0, "note": "이번 실행에서 제외"}
    kr = empty
    us = empty
    if args.market in ("kr", "all"):
        from . import kr_screener
        kr = _run_market("한국", kr_screener.screen)
    if args.market in ("us", "all"):
        from . import us_screener
        us = _run_market("미국", us_screener.screen)

    report_date = datetime.now(KST).strftime("%Y-%m-%d")
    markdown = build_report(kr, us, report_date, dry_run=args.dry_run)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{report_date}.md"
    out_path.write_text(markdown, encoding="utf-8")
    print(f"[info] 리포트 저장: {out_path}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"report_path={out_path}\n")
            fh.write(f"report_title=주식 분석 리포트 {report_date}\n")
            fh.write(f"report_date={report_date}\n")


if __name__ == "__main__":
    main()
