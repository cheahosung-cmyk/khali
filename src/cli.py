"""Khali 상가건물 관리비 정산 에이전트 CLI.

사용 예
-------
호실별 고지서 산출:
    khali settle --units units.csv --costs costs.csv --meters meters.csv --out bills.csv

샘플(웰스타임 빌딩) 입력 파일 생성:
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
from .notice import format_notices, write_notices


def _won(n: int) -> str:
    return f"{n:,}원"


def _print_summary(settlement: Settlement) -> None:
    use_vat = settlement.vat_rate > 0
    print("\n============== 상가 관리비 정산 요약 ==============")
    print(f" 호실 수      : 총 {len(settlement.bills)}호실 "
          f"(임차 {len(settlement.tenant_bills)} / 공실 {len(settlement.vacant_bills)})")
    print(f" 건물 총액    : {_won(settlement.building_total)}")
    print("--------------------------------------------------")
    print(" [항목별 총액 / 배분방식]")
    for item in settlement.items:
        rate = f"  (@{item.rate:,.0f})" if item.rate else ""
        print(f"   - {item.name:<16} {item.method.value:<6} {_won(item.total):>14}{rate}")
    print("--------------------------------------------------")
    print(" [청구 요약]")
    if use_vat:
        print(f"   임차인 공급가액 합계 : {_won(settlement.supply_billed_total)}")
        print(f"   부가세(VAT {int(settlement.vat_rate*100)}%)    : {_won(settlement.vat_total)}")
        print(f"   임차인 청구 총액     : {_won(settlement.billed_grand_total)}")
    else:
        print(f"   임차인 청구 합계     : {_won(settlement.supply_billed_total)}")
    if settlement.has_vacant:
        print(f"   건물주 부담(공실)    : {_won(settlement.owner_borne_total)}  ← 참고")
    print("--------------------------------------------------")

    problems = settlement.verify()
    if problems:
        print(" ⚠ 정산 검증 실패:")
        for p in problems:
            print(f"   {p}")
    else:
        print(" ✅ 정산 검증 통과 (항목별 합계 = 총액, 호실 합계 = 건물총액)")
    print("==================================================\n")


def _preview_bills(settlement: Settlement, limit: int = 12) -> None:
    use_vat = settlement.vat_rate > 0
    print(f" [호실별 고지서 미리보기]")
    for bill in settlement.tenant_bills[:limit]:
        if use_vat:
            line = (f"공급 {_won(bill.supply)} + VAT {_won(settlement.vat(bill))} "
                    f"= {_won(settlement.billed_total(bill))}")
        else:
            line = f"합계 {_won(bill.supply)}"
        print(f"   · {bill.unit.name:<12} ({bill.unit.area:>5g}평)  {line}")
    extra = len(settlement.tenant_bills) - limit
    if extra > 0:
        print(f"   · ... 외 {extra}호실 (전체는 출력 CSV 참고)")
    print()


def cmd_settle(args: argparse.Namespace) -> int:
    units = read_units(args.units)
    items = read_costs(args.costs)
    usage = read_meters(args.meters) if args.meters else {}

    settlement = settle(units, items, usage, vat_rate=args.vat_rate)
    write_bills(args.out, settlement)

    _print_summary(settlement)
    _preview_bills(settlement)
    print(f" 💾 호실별 고지서 저장 완료 → {args.out}")

    return 0 if not settlement.verify() else 1


def cmd_notice(args: argparse.Namespace) -> int:
    units = read_units(args.units)
    items = read_costs(args.costs)
    usage = read_meters(args.meters) if args.meters else {}

    settlement = settle(units, items, usage, vat_rate=args.vat_rate)
    text = format_notices(settlement, title=args.title,
                          account=args.account or "", due=args.due or "")
    write_notices(args.out, text)

    print(text)
    print(f"\n 💾 카톡 발송용 텍스트 저장 완료 → {args.out}")
    print(f"    (호실별 블록을 복사해 카카오톡/문자로 보내세요)")
    return 0 if not settlement.verify() else 1


def cmd_sample(args: argparse.Namespace) -> int:
    """웰스타임 빌딩 2024년 12월 기준 예시 입력 파일을 생성한다."""
    os.makedirs(args.dir, exist_ok=True)

    # 호실, 분양평수 (총 1,006평)
    units = [
        ("원유로", 44),
        ("와플칸", 10),
        ("에바돈카츠", 31),
        ("드림스터디", 207),
        ("아기고래", 62),
        ("카카오3F", 207),
        ("영동스크린4F", 207),
        ("명성화로", 207),
        ("코리아독스", 31),
    ]
    units_csv = "호실,평수,입주여부\n"
    for name, area in units:
        units_csv += f"{name},{area},Y\n"

    # 항목, 총액, 배분방식, 단가
    #  - 일반관리비: 평당 4,000원 (단가 방식 → 총액 자동 산출)
    #  - 공동전기료: 기본/전력량/공용을 평수 비례 배분
    #  - 공동수도료: 세대분(검침 사용량) + 공용분(평수 비례)
    costs = [
        ("일반관리비", "", "면적", "4000"),
        ("공동전기료(기본)", "203280", "면적", ""),
        ("공동전기료(전력량)", "569470", "면적", ""),
        ("공동전기료(공용)", "22440", "면적", ""),
        ("공동수도료(세대)", "417566", "사용량", ""),
        ("공동수도료(공용)", "313914", "면적", ""),
    ]
    costs_csv = "항목,총액,배분방식,단가\n"
    for name, total, method, rate in costs:
        costs_csv += f"{name},{total},{method},{rate}\n"

    # 세대 수도 검침 사용량 (합계 141)
    water = [
        ("원유로", 11), ("와플칸", 0), ("에바돈카츠", 51),
        ("드림스터디", 1), ("아기고래", 11), ("카카오3F", 6),
        ("영동스크린4F", 0), ("명성화로", 61), ("코리아독스", 0),
    ]
    meters_csv = "호실,항목,사용량\n"
    for name, amt in water:
        meters_csv += f"{name},공동수도료(세대),{amt}\n"

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
        description="상가건물 관리비 정산 에이전트 - 호실 정보·비용·검침값으로 호실별 고지서를 자동 산출",
    )
    parser.add_argument("--version", action="version", version=f"khali {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_settle = sub.add_parser("settle", help="관리비 정산 실행")
    p_settle.add_argument("--units", required=True, help="호실 정보 CSV (호실,평수,입주여부)")
    p_settle.add_argument("--costs", required=True, help="비용 항목 CSV (항목,총액,배분방식,단가)")
    p_settle.add_argument("--meters", help="검침값 CSV (호실,항목,사용량) - 사용량 항목이 있을 때")
    p_settle.add_argument("--out", default="bills.csv", help="출력 고지서 CSV 경로 (기본: bills.csv)")
    p_settle.add_argument("--vat-rate", type=float, default=0.0,
                          help="부가가치세율 (기본: 0=미적용). 예: 0.1")
    p_settle.set_defaults(func=cmd_settle)

    p_notice = sub.add_parser("notice", help="카카오톡 발송용 고지 텍스트 생성")
    p_notice.add_argument("--units", required=True, help="호실 정보 CSV (호실,평수,입주여부)")
    p_notice.add_argument("--costs", required=True, help="비용 항목 CSV (항목,총액,배분방식,단가)")
    p_notice.add_argument("--meters", help="검침값 CSV (호실,항목,사용량)")
    p_notice.add_argument("--out", default="notices.txt", help="출력 텍스트 파일 (기본: notices.txt)")
    p_notice.add_argument("--title", default="관리비 안내", help="고지서 제목 (예: '웰스타임 2024년 12월 관리비')")
    p_notice.add_argument("--account", help="입금계좌 안내 문구")
    p_notice.add_argument("--due", help="납부기한 안내 문구")
    p_notice.add_argument("--vat-rate", type=float, default=0.0, help="부가가치세율 (기본: 0=미적용)")
    p_notice.set_defaults(func=cmd_notice)

    p_sample = sub.add_parser("sample", help="예시(웰스타임) 입력 파일 생성")
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
