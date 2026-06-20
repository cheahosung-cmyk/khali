"""Khali 관리비 정산 에이전트 CLI.

사용 예
-------
세대별 고지서 산출:
    khali settle --units units.csv --costs costs.csv --meters meters.csv --out bills.csv

샘플 입력 파일 생성:
    khali sample --dir ./sample
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .calculator import settle
from .io_utils import read_costs, read_meters, read_units, write_bills
from .models import Settlement


def _won(n: int) -> str:
    return f"{n:,}원"


def _print_summary(settlement: Settlement) -> None:
    print("\n================ 관리비 정산 요약 ================")
    print(f" 세대 수      : {len(settlement.bills):,}세대")
    print(f" 부과 총액    : {_won(settlement.grand_total)}")
    print("-------------------------------------------------")
    print(" [항목별 부과액]")
    for item in settlement.items:
        charged = settlement.item_total_charged(item.name)
        print(f"   - {item.name:<14} {item.method.value:<6} {_won(charged):>16}")
    print("-------------------------------------------------")

    problems = settlement.verify()
    if problems:
        print(" ⚠ 정산 검증 실패:")
        for p in problems:
            print(f"   {p}")
    else:
        print(" ✅ 정산 검증 통과 (항목별 합계 = 입력 총액)")
    print("=================================================\n")


def _preview_bills(settlement: Settlement, limit: int = 5) -> None:
    print(f" [세대별 고지서 미리보기 (상위 {limit}세대)]")
    for bill in settlement.bills[:limit]:
        print(f"   · {bill.unit.name:<12} 합계 {_won(bill.total)}")
    if len(settlement.bills) > limit:
        print(f"   · ... 외 {len(settlement.bills) - limit:,}세대 (전체는 출력 CSV 참고)")
    print()


def cmd_settle(args: argparse.Namespace) -> int:
    units = read_units(args.units)
    items = read_costs(args.costs)
    usage = read_meters(args.meters) if args.meters else {}

    settlement = settle(units, items, usage)
    write_bills(args.out, settlement)

    _print_summary(settlement)
    _preview_bills(settlement)
    print(f" 💾 세대별 고지서 저장 완료 → {args.out}")

    return 0 if not settlement.verify() else 1


def cmd_sample(args: argparse.Namespace) -> int:
    os.makedirs(args.dir, exist_ok=True)

    units_csv = "동,호,전용면적,입주여부\n"
    costs_csv = "항목,총액,배분방식\n"
    meters_csv = "동,호,항목,사용량\n"

    # 예시: 101동 4세대 (1세대 공실)
    sample_units = [
        ("101", "1501", 84.97, "Y"),
        ("101", "1502", 84.97, "Y"),
        ("101", "1601", 59.95, "Y"),
        ("101", "1602", 59.95, "N"),  # 공실
    ]
    for d, h, a, o in sample_units:
        units_csv += f"{d},{h},{a},{o}\n"

    sample_costs = [
        ("일반관리비", "3500000", "면적"),
        ("청소비", "1200000", "세대균등"),
        ("승강기유지비", "800000", "입주균등"),
        ("공동전기료", "650000", "면적"),
        ("세대전기료", "1280000", "사용량"),
        ("수도료", "430000", "사용량"),
        ("장기수선충당금", "2000000", "면적"),
    ]
    for name, total, method in sample_costs:
        costs_csv += f"{name},{total},{method}\n"

    # 사용량 비례 항목(세대전기료/수도료) 검침값
    sample_meters = [
        ("101", "1501", "세대전기료", 320),
        ("101", "1502", "세대전기료", 280),
        ("101", "1601", "세대전기료", 410),
        ("101", "1602", "세대전기료", 0),  # 공실
        ("101", "1501", "수도료", 18),
        ("101", "1502", "수도료", 22),
        ("101", "1601", "수도료", 15),
        ("101", "1602", "수도료", 0),
    ]
    for d, h, item, amt in sample_meters:
        meters_csv += f"{d},{h},{item},{amt}\n"

    paths = {
        os.path.join(args.dir, "units.csv"): units_csv,
        os.path.join(args.dir, "costs.csv"): costs_csv,
        os.path.join(args.dir, "meters.csv"): meters_csv,
    }
    for path, content in paths.items():
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(content)
        print(f" 💾 생성: {path}")

    print(
        "\n 다음 명령으로 정산을 실행하세요:\n"
        f"   khali settle "
        f"--units {os.path.join(args.dir, 'units.csv')} "
        f"--costs {os.path.join(args.dir, 'costs.csv')} "
        f"--meters {os.path.join(args.dir, 'meters.csv')} "
        f"--out {os.path.join(args.dir, 'bills.csv')}\n"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="khali",
        description="관리비 정산 에이전트 - 세대 정보·비용·검침값으로 세대별 고지서를 자동 산출",
    )
    parser.add_argument("--version", action="version", version=f"khali {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_settle = sub.add_parser("settle", help="관리비 정산 실행")
    p_settle.add_argument("--units", required=True, help="세대 정보 CSV (동,호,전용면적,입주여부)")
    p_settle.add_argument("--costs", required=True, help="비용 항목 CSV (항목,총액,배분방식)")
    p_settle.add_argument("--meters", help="검침값 CSV (동,호,항목,사용량) - 사용량 항목이 있을 때")
    p_settle.add_argument("--out", default="bills.csv", help="출력 고지서 CSV 경로 (기본: bills.csv)")
    p_settle.set_defaults(func=cmd_settle)

    p_sample = sub.add_parser("sample", help="예시 입력 파일 생성")
    p_sample.add_argument("--dir", default="sample", help="샘플 파일 생성 폴더 (기본: sample)")
    p_sample.set_defaults(func=cmd_sample)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as e:
        print(f" ❌ 오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
