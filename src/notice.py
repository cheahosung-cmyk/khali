"""카카오톡 발송용 관리비 고지 텍스트 생성.

호실별로 그대로 복사해 카카오톡/문자로 보낼 수 있는 텍스트를 만든다.
(카카오톡은 가변폭 글꼴이라 표 정렬 대신 '항목 : 금액' 형식으로 구성)
"""

from __future__ import annotations

from typing import List

from .models import Settlement


def _won(n: int) -> str:
    return f"{n:,}원"


def format_notice(settlement: Settlement, bill, title: str,
                  account: str = "", due: str = "") -> str:
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

    if account or due:
        lines.append("")
    if account:
        lines.append(f"입금계좌: {account}")
    if due:
        lines.append(f"납부기한: {due}")
    lines.append("감사합니다.")
    return "\n".join(lines)


def format_notices(settlement: Settlement, title: str = "관리비 안내",
                   account: str = "", due: str = "") -> str:
    """모든 임차 호실의 발송용 텍스트를 구분선과 함께 이어 붙인다."""
    tenants = settlement.tenant_bills
    total = len(tenants)
    blocks: List[str] = []
    for i, bill in enumerate(tenants, 1):
        divider = f"━━━━━━━━━ ({i}/{total}) {bill.unit.name} ━━━━━━━━━"
        blocks.append(divider + "\n" + format_notice(settlement, bill, title, account, due))

    # 관리소장 확인용 합계
    summary = [
        "═════════ [관리소장 확인용] ═════════",
        f"발송 대상 : {total}호실",
        f"청구 합계 : {_won(settlement.billed_grand_total if settlement.vat_rate > 0 else settlement.supply_billed_total)}",
    ]
    if settlement.has_vacant:
        summary.append(f"건물주 부담(공실) : {_won(settlement.owner_borne_total)}")
    blocks.append("\n".join(summary))

    return "\n\n".join(blocks) + "\n"


def write_notices(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
