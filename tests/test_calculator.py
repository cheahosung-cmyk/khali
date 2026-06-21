"""상가 관리비 정산 엔진 테스트 (웰스타임 빌딩 기준).

표준 라이브러리만으로 실행 가능: `python -m pytest` 또는 `python -m unittest`.
"""

import unittest

from src.calculator import allocate, settle
from src.invoice import build_invoice_html
from src.notice import format_notices
from src.models import AllocationMethod, CostItem, Unit, round_won


# 웰스타임 빌딩 호실/평수 (총 1,006평)
WELLSTIME = [
    Unit("원유로", 44),
    Unit("와플칸", 10),
    Unit("에바돈카츠", 31),
    Unit("드림스터디", 207),
    Unit("아기고래", 62),
    Unit("카카오3F", 207),
    Unit("영동스크린4F", 207),
    Unit("명성화로", 207),
    Unit("코리아독스", 31),
]


class TestAllocate(unittest.TestCase):
    def test_sum_matches_total_exactly(self):
        weights = {u.key: u.area for u in WELLSTIME}
        result = allocate(795_190, weights)
        self.assertEqual(sum(result.values()), 795_190)

    def test_equal_weights(self):
        result = allocate(100, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(sum(result.values()), 100)
        self.assertEqual(sorted(result.values()), [33, 33, 34])

    def test_zero_weight_gets_nothing(self):
        result = allocate(1000, {"a": 0, "b": 10, "c": 0})
        self.assertEqual(result["b"], 1000)
        self.assertEqual(result["a"], 0)


class TestRoundWon(unittest.TestCase):
    def test_round_half_up(self):
        self.assertEqual(round_won(100.4), 100)
        self.assertEqual(round_won(100.5), 101)


class TestGeneralManagementFee(unittest.TestCase):
    """일반관리비 = 평수 × 4,000원 (단가 방식) — 기존 정산표와 정확히 일치해야 함."""

    def test_rate_based_exact(self):
        items = [CostItem("일반관리비", 0, AllocationMethod.AREA, rate=4000)]
        s = settle(WELLSTIME, items)
        bills = {b.unit.name: b.supply for b in s.bills}
        self.assertEqual(bills["원유로"], 176_000)      # 44 × 4000
        self.assertEqual(bills["와플칸"], 40_000)       # 10 × 4000
        self.assertEqual(bills["드림스터디"], 828_000)  # 207 × 4000
        self.assertEqual(s.building_total, 4_024_000)   # 1006 × 4000
        self.assertEqual(s.verify(), [])


class TestSettle(unittest.TestCase):
    def setUp(self):
        self.usage = {
            "원유로": {"공동수도료(세대)": 11},
            "에바돈카츠": {"공동수도료(세대)": 51},
            "명성화로": {"공동수도료(세대)": 61},
            "드림스터디": {"공동수도료(세대)": 1},
            "아기고래": {"공동수도료(세대)": 11},
            "카카오3F": {"공동수도료(세대)": 6},
        }

    def test_electricity_area_total_matches(self):
        items = [CostItem("공동전기료", 795_190, AllocationMethod.AREA)]
        s = settle(WELLSTIME, items)
        self.assertEqual(s.item_total_charged("공동전기료"), 795_190)
        self.assertEqual(s.verify(), [])

    def test_water_usage_allocation(self):
        items = [CostItem("공동수도료(세대)", 417_566, AllocationMethod.USAGE)]
        s = settle(WELLSTIME, items, self.usage)
        self.assertEqual(s.item_total_charged("공동수도료(세대)"), 417_566)
        # 사용량 0 호실은 0원
        zero = next(b for b in s.bills if b.unit.name == "코리아독스")
        self.assertEqual(zero.supply, 0)
        # 사용량 최다(명성화로 61)가 최다 부담
        most = next(b for b in s.bills if b.unit.name == "명성화로")
        self.assertEqual(most.supply, round(61 / 141 * 417_566))

    def test_full_settlement_verifies(self):
        items = [
            CostItem("일반관리비", 0, AllocationMethod.AREA, rate=4000),
            CostItem("공동전기료", 795_190, AllocationMethod.AREA),
            CostItem("공동수도료(세대)", 417_566, AllocationMethod.USAGE),
            CostItem("공동수도료(공용)", 313_914, AllocationMethod.AREA),
        ]
        s = settle(WELLSTIME, items, self.usage)
        self.assertEqual(s.building_total, 4_024_000 + 795_190 + 417_566 + 313_914)
        self.assertEqual(s.verify(), [])

    def test_vacant_owner_borne(self):
        units = [Unit("A", 100, True), Unit("B", 100, False)]
        items = [CostItem("청소비", 200_000, AllocationMethod.AREA)]
        s = settle(units, items)
        self.assertEqual(s.supply_billed_total, 100_000)      # 임차 A
        self.assertEqual(s.owner_borne_total, 100_000)        # 공실 B = 건물주
        self.assertEqual(s.verify(), [])

    def test_vat_optional(self):
        items = [CostItem("일반관리비", 0, AllocationMethod.AREA, rate=4000)]
        s = settle(WELLSTIME, items, vat_rate=0.1)
        b = next(x for x in s.bills if x.unit.name == "원유로")
        self.assertEqual(s.vat(b), round_won(176_000 * 0.1))
        self.assertEqual(s.billed_total(b), 176_000 + 17_600)

    def test_empty_units_raises(self):
        with self.assertRaises(ValueError):
            settle([], [CostItem("청소비", 100, AllocationMethod.AREA)])


class TestOutputs(unittest.TestCase):
    def setUp(self):
        self.units = [Unit("원유로", 44), Unit("드림스터디", 207)]
        self.items = [CostItem("일반관리비", 0, AllocationMethod.AREA, rate=4000)]
        self.s = settle(self.units, self.items)

    def test_notice_contains_amounts_and_diff(self):
        prev = {"원유로": 170_000}  # 전월 176,000보다 적음 → 증가
        text = format_notices(self.s, title="테스트", prev=prev)
        self.assertIn("원유로", text)
        self.assertIn("176,000원", text)
        self.assertIn("▲", text)  # 전월 대비 증가 표시
        self.assertIn("관리소장 확인용", text)

    def test_invoice_html_structure(self):
        html = build_invoice_html(self.s, title="테스트")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("원유로", html)
        self.assertIn("드림스터디", html)
        self.assertIn("page-break-after", html)


if __name__ == "__main__":
    unittest.main()
