"""Khali 상가건물 관리비 정산 에이전트 CLI.

사용 예
-------
호실별 고지서 산출:
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
    print("\n============== 상가 관리비 정산 요약 ==============")
    print(f" 호실 수      : 총 {len(settlement.bills)}호실 "
          f"(임차 {len(settlement.tenant_bills)} / 공실 {len(settlement.vacant_bills)})")
    print(f" 건물 총액    : {_won(settlement.building_total)} (공급가액)")
    print("--------------------------------------------------")
    print(" [항목별 총액 / 배분방식]")
    for item in settlement.items:
        print(f"   - {item.name:<14} {item.method.value:<6} {_won(item.total):>16}")
    print("--------------------------------------------------")
    print(" [청구 요약]")
    print(f"   임차인 공급가액 합계 : {_won(settlement.supply_billed_total)}")
    print(f"   부가세(VAT {int(settlement.vat_rate*100)}%)    : {_won(settlement.vat_total)}")
    print(f"   임차인 청구 총액     : {_won(settlement.billed_grand_total)}")
    print(f"   건물주 부담(공실)    : {_won(settlement.owner_borne_total)}  ← 참고")
    print("--------------------------------------------------")

    problems = settlement.verify()
    if problems:
        print(" ⚠ 정산 검증 실패:")
        for p in problems:
            print(f"   {p}")
    else:
        print(" ✅ 정산 검증 통과 (항목별 합계 = 입력 총액, 임차인+공실 = 건물총액)")
    print("==================================================\n")


def _preview_bills(settlement: Settlement, limit: int = 6) -> None:
    print(f" [임차인 고지서 미리보기 (상위 {limit}호실)]")
    for bill in settlement.tenant_bills[:limit]:
        vat = settlement.vat(bill)
        total = settlement.billed_total(bill)
        tenant = bill.unit.tenant or "-"
        print(f"   · {bill.unit.name:<10} {tenant:<10} "
              f"공급 {_won(bill.supply)} + VAT {_won(vat)} = {_won(total)}")
    extra = len(settlement.tenant_bills) - limit
    if extra > 0:
        print(f"   · ... 외 {extra}호실 (전체는 출력 CSV 참고)")
    print()


def cmd_settle(args: argparse.Namespace) -> int:
    units = read_units(args.units)
    items = read_costs(args.costs)
    usage = read_meters(args.meters) if args.meters else {}

    vat_rate = 0.0 if args.no_vat else args.vat_rate
    settlement = settle(units, items, usage, vat_rate=vat_rate)
    write_bills(args.out, settlement)

    _print_summary(settlement)
    _preview_bills(settlement)
    print(f" 💾 호실별 고지서 저장 완료 → {args.out}")

    return 0 if not settlement.verify() else 1


def cmd_sample(args: argparse.Namespace) -> int:
    os.makedirs(args.dir, exist_ok=True)

    # 예시: 5층 상가건물 (1층 2호실, 2~5층 각 1호실, 일부 공실)
    sample_units = [
        ("1", "101", 66.1, "행복편의점", "Y"),
        ("1", "102", 49.5, "민들레카페", "Y"),
        ("2", "201", 99.2, "튼튼정형외과", "Y"),
        ("3", "301", 99.2, "", "N"),  # 공실
        ("4", "401", 99.2, "한빛세무회계", "Y"),
        ("5", "501", 132.3, "스카이학원", "Y"),
    ]
    units_csv = "층,호,계약면적,임차인,입주여부\n"
    for floor, ho, area, tenant, occ in sample_units:
        units_csv += f"{floor},{ho},{area},{tenant},{occ}\n"

    sample_costs = [
        ("일반관리비", "1800000", "면적"),
        ("청소비", "600000", "호실균등"),
        ("공용전기료", "450000", "면적"),
        ("승강기유지비", "300000", "면적"),
        ("정화조관리비", "150000", "호실균등"),
        ("호실전기료", "1650000", "사용량"),
        ("수도료", "320000", "사용량"),
    ]
    costs_csv = "항목,총액,배분방식\n"
    for name, total, method in sample_costs:
        costs_csv += f"{name},{total},{method}\n"

    # 사용량 비례 항목(호실전기료/수도료) 검침값 — 공실(301)은 0
    sample_meters = [
        ("1", "101", "호실전기료", 540),
        ("1", "102", "호실전기료", 380),
        ("2", "201", "호실전기료", 720),
        ("3", "301", "호실전기료", 0),
        ("4", "401", "호실전기료", 410),
        ("5", "501", "호실전기료", 950),
        ("1", "101", "수도료", 22),
        ("1", "102", "수도료", 31),
        ("2", "201", "수도료", 18),
        ("3", "301", "수도료", 0),
        ("4", "401", "수도료", 9),
        ("5", "501", "수도료", 25),
    ]
    meters_csv = "층,호,항목,사용량\n"
    for floor, ho, item, amt in sample_meters:
        meters_csv += f"{floor},{ho},{item},{amt}\n"

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
        description="상가건물 관리비 정산 에이전트 - 호실 정보·비용·검침값으로 임차인별 고지서를 자동 산출",
    )
    parser.add_argument("--version", action="version", version=f"khali {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_settle = sub.add_parser("settle", help="관리비 정산 실행")
    p_settle.add_argument("--units", required=True, help="호실 정보 CSV (층,호,계약면적,임차인,입주여부)")
    p_settle.add_argument("--costs", required=True, help="비용 항목 CSV (항목,총액,배분방식)")
    p_settle.add_argument("--meters", help="검침값 CSV (층,호,항목,사용량) - 사용량 항목이 있을 때")
    p_settle.add_argument("--out", default="bills.csv", help="출력 고지서 CSV 경로 (기본: bills.csv)")
    p_settle.add_argument("--vat-rate", type=float, default=0.1, help="부가가치세율 (기본: 0.1)")
    p_settle.add_argument("--no-vat", action="store_true", help="부가세 미적용(간이/면세 등)")
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
