"""인쇄용 HTML 관리비 고지서 생성.

브라우저에서 열어 인쇄하거나 PDF로 저장할 수 있는 고지서를 만든다.
호실마다 한 장씩 페이지가 나뉘며(@media print), 별도 라이브러리가 필요 없다.
"""

from __future__ import annotations

import html
from typing import Dict, Optional

from .models import Settlement


def _won(n: int) -> str:
    return f"{n:,}원"


_CSS = """
* { box-sizing: border-box; }
body { font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; margin: 0; background: #f0f0f0; color: #222; }
.sheet { width: 720px; margin: 16px auto; background: #fff; padding: 36px 44px;
         box-shadow: 0 1px 6px rgba(0,0,0,.15); page-break-after: always; }
.sheet:last-child { page-break-after: auto; }
h1 { font-size: 22px; text-align: center; margin: 0 0 4px; letter-spacing: 2px; }
.sub { text-align: center; color: #666; margin: 0 0 24px; font-size: 13px; }
.unit { font-size: 18px; font-weight: 700; margin: 0 0 12px; padding-bottom: 8px;
        border-bottom: 2px solid #333; }
table { width: 100%; border-collapse: collapse; margin-bottom: 18px; }
th, td { padding: 9px 12px; font-size: 14px; border-bottom: 1px solid #e0e0e0; }
th { text-align: left; background: #fafafa; color: #555; font-weight: 600; }
td.amt { text-align: right; font-variant-numeric: tabular-nums; }
tr.total td { font-size: 17px; font-weight: 700; border-top: 2px solid #333;
              border-bottom: none; background: #f7f9ff; }
.diff { text-align: right; font-size: 13px; margin: -8px 0 18px; }
.up { color: #c0392b; } .down { color: #2471a3; } .same { color: #888; }
.pay { background: #f7f7f7; border-radius: 8px; padding: 14px 18px; font-size: 13px; line-height: 1.7; }
.pay b { color: #000; }
@media print {
  body { background: #fff; }
  .sheet { box-shadow: none; margin: 0; width: auto; }
}
"""


def _diff_html(diff: int) -> str:
    if diff > 0:
        return f'<div class="diff up">전월 대비 ▲ {diff:,}원 증가</div>'
    if diff < 0:
        return f'<div class="diff down">전월 대비 ▼ {abs(diff):,}원 감소</div>'
    return '<div class="diff same">전월 대비 변동 없음</div>'


def _sheet(settlement: Settlement, bill, title: str, account: str, due: str,
           prev_total: Optional[int]) -> str:
    u = bill.unit
    use_vat = settlement.vat_rate > 0
    rows = "".join(
        f"<tr><td>{html.escape(item.name)}</td>"
        f'<td class="amt">{_won(bill.charges.get(item.name, 0))}</td></tr>'
        for item in settlement.items
    )
    if use_vat:
        rows += (
            f'<tr><td>공급가액</td><td class="amt">{_won(bill.supply)}</td></tr>'
            f'<tr><td>부가세</td><td class="amt">{_won(settlement.vat(bill))}</td></tr>'
            f'<tr class="total"><td>청구합계</td><td class="amt">{_won(settlement.billed_total(bill))}</td></tr>'
        )
    else:
        rows += f'<tr class="total"><td>합계</td><td class="amt">{_won(bill.supply)}</td></tr>'

    diff = _diff_html(settlement.claim(bill) - prev_total) if prev_total is not None else ""

    pay = []
    if account:
        pay.append(f"입금계좌 : <b>{html.escape(account)}</b>")
    if due:
        pay.append(f"납부기한 : <b>{html.escape(due)}</b>")
    pay_html = f'<div class="pay">{"<br>".join(pay)}</div>' if pay else ""

    return f"""
  <div class="sheet">
    <h1>관 리 비 고 지 서</h1>
    <p class="sub">{html.escape(title)}</p>
    <div class="unit">{html.escape(u.name)} &nbsp;({u.area:g}평)</div>
    <table>
      <tr><th>항목</th><th style="text-align:right">금액</th></tr>
      {rows}
    </table>
    {diff}
    {pay_html}
  </div>"""


def build_invoice_html(settlement: Settlement, title: str = "관리비 고지서",
                       account: str = "", due: str = "",
                       prev: Optional[Dict[str, int]] = None) -> str:
    prev = prev or {}
    sheets = "".join(
        _sheet(settlement, bill, title, account, due, prev.get(bill.unit.name))
        for bill in settlement.tenant_bills
    )
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{_CSS}</style></head>
<body>{sheets}
</body></html>"""


def write_invoice(path: str, html_text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
