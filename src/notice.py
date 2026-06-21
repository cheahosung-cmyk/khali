"""카카오톡 발송용 관리비 고지 텍스트 생성.

호실별로 그대로 복사해 카카오톡/문자로 보낼 수 있는 텍스트를 만든다.
(카카오톡은 가변폭 글꼴이라 표 정렬 대신 '항목 : 금액' 형식으로 구성)
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from .models import Settlement


def _won(n: int) -> str:
    return f"{n:,}원"


def _diff_text(diff: int) -> str:
    if diff > 0:
        return f"전월 대비 : ▲ {diff:,}원 증가"
    if diff < 0:
        return f"전월 대비 : ▼ {abs(diff):,}원 감소"
    return "전월 대비 : 변동 없음"


def format_notice(settlement: Settlement, bill, title: str,
                  account: str = "", due: str = "",
                  prev_total: Optional[int] = None) -> str:
    """호실 1곳의 발송용 텍스트(블록 하나)를 만든다."""
    u = bill.unit
    use_vat = settlement.vat_rate > 0
    lines: List[str] = [f"[{title}]", f"{u.name} ({u.area:g}평)", ""]

    for item in settlement.items:
        lines.append(f"· {item.name} : {_won(bill.charges.get(item.name, 0))}")
    lines.append("")

    if use_vat:
        lines.append(f"공급가액 : {_won(bill.supply)}")
        lines.append(f"부가세 : {_won(settlement.vat(bill))}")
        lines.append(f"▶ 청구합계 : {_won(settlement.billed_total(bill))}")
    else:
        lines.append(f"▶ 합계 : {_won(bill.supply)}")

    if prev_total is not None:
        lines.append(_diff_text(settlement.claim(bill) - prev_total))

    if account or due:
        lines.append("")
    if account:
        lines.append(f"입금계좌: {account}")
    if due:
        lines.append(f"납부기한: {due}")
    lines.append("감사합니다.")
    return "\n".join(lines)


def format_notices(settlement: Settlement, title: str = "관리비 안내",
                   account: str = "", due: str = "",
                   prev: Optional[Dict[str, int]] = None) -> str:
    """모든 임차 호실의 발송용 텍스트를 구분선과 함께 이어 붙인다."""
    prev = prev or {}
    tenants = settlement.tenant_bills
    total = len(tenants)
    blocks: List[str] = []
    for i, bill in enumerate(tenants, 1):
        divider = f"━━━━━━━━━ ({i}/{total}) {bill.unit.name} ━━━━━━━━━"
        body = format_notice(settlement, bill, title, account, due,
                             prev.get(bill.unit.name))
        blocks.append(divider + "\n" + body)

    claim_sum = settlement.billed_grand_total if settlement.vat_rate > 0 else settlement.supply_billed_total
    summary = [
        "═════════ [관리소장 확인용] ═════════",
        f"발송 대상 : {total}호실",
        f"청구 합계 : {_won(claim_sum)}",
    ]
    if prev:
        prev_sum = sum(prev.get(b.unit.name, 0) for b in tenants)
        cur_sum = sum(settlement.claim(b) for b in tenants if b.unit.name in prev)
        summary.append(f"전월 대비 : {cur_sum - prev_sum:+,}원")
    if settlement.has_vacant:
        summary.append(f"건물주 부담(공실) : {_won(settlement.owner_borne_total)}")
    blocks.append("\n".join(summary))

    return "\n\n".join(blocks) + "\n"


def write_notices(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _safe_filename(name: str) -> str:
    """파일명에 쓸 수 없는 문자를 정리한다."""
    return re.sub(r"[^\w가-힣A-Za-z0-9._-]", "_", name)


def write_split_notices(out_dir: str, settlement: Settlement, title: str = "관리비 안내",
                        account: str = "", due: str = "",
                        prev: Optional[Dict[str, int]] = None) -> List[str]:
    """호실별로 개별 .txt 파일을 만든다. 생성된 파일 경로 목록을 반환."""
    prev = prev or {}
    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []
    for i, bill in enumerate(settlement.tenant_bills, 1):
        body = format_notice(settlement, bill, title, account, due,
                             prev.get(bill.unit.name))
        fname = f"{i:02d}_{_safe_filename(bill.unit.name)}.txt"
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body + "\n")
        paths.append(path)
    return paths
