"""정산 엔진 테스트.

표준 라이브러리만으로 실행 가능: `python -m pytest` 또는 `python -m unittest`.
"""

import unittest

from src.calculator import allocate, settle
from src.models import AllocationMethod, CostItem, Unit


class TestAllocate(unittest.TestCase):
    def test_sum_matches_total_exactly(self):
        # 1원 단위로 안 떨어지는 금액도 합계가 정확히 일치해야 한다.
        weights = {"a": 84.97, "b": 84.97, "c": 59.95}
        result = allocate(1_000_000, weights)
        self.assertEqual(sum(result.values()), 1_000_000)

    def test_equal_weights(self):
        result = allocate(100, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(sum(result.values()), 100)
        # 100 / 3 = 33.33 -> 34,33,33 (잔여 1원이 1세대에 배분)
        self.assertEqual(sorted(result.values()), [33, 33, 34])

    def test_zero_weight_gets_nothing(self):
        result = allocate(1000, {"a": 0, "b": 10, "c": 0})
        self.assertEqual(result["a"], 0)
        self.assertEqual(result["c"], 0)
        self.assertEqual(result["b"], 1000)

    def test_no_weight_total_zero(self):
        result = allocate(1000, {"a": 0, "b": 0})
        self.assertEqual(result, {"a": 0, "b": 0})


class TestSettle(unittest.TestCase):
    def setUp(self):
        self.units = [
            Unit("101", "1501", 84.97, True),
            Unit("101", "1502", 84.97, True),
            Unit("101", "1601", 59.95, True),
            Unit("101", "1602", 59.95, False),  # 공실
        ]
        self.usage = {
            "101-1501": {"세대전기료": 320},
            "101-1502": {"세대전기료": 280},
            "101-1601": {"세대전기료": 410},
            "101-1602": {"세대전기료": 0},
        }

    def test_area_allocation_total_matches(self):
        items = [CostItem("일반관리비", 3_500_000, AllocationMethod.AREA)]
        s = settle(self.units, items, self.usage)
        self.assertEqual(s.item_total_charged("일반관리비"), 3_500_000)
        self.assertEqual(s.verify(), [])

    def test_occupied_only_pays(self):
        items = [CostItem("승강기유지비", 800_000, AllocationMethod.OCCUPIED)]
        s = settle(self.units, items, self.usage)
        # 공실(101-1602)은 0원
        vacant = next(b for b in s.bills if b.unit.key == "101-1602")
        self.assertEqual(vacant.charges["승강기유지비"], 0)
        # 입주 3세대가 균등 분담
        self.assertEqual(s.item_total_charged("승강기유지비"), 800_000)

    def test_usage_allocation(self):
        items = [CostItem("세대전기료", 1_280_000, AllocationMethod.USAGE)]
        s = settle(self.units, items, self.usage)
        self.assertEqual(s.item_total_charged("세대전기료"), 1_280_000)
        # 사용량 0인 공실은 0원
        vacant = next(b for b in s.bills if b.unit.key == "101-1602")
        self.assertEqual(vacant.charges["세대전기료"], 0)
        # 사용량이 가장 많은 세대가 가장 많이 부담
        b1601 = next(b for b in s.bills if b.unit.key == "101-1601")
        b1502 = next(b for b in s.bills if b.unit.key == "101-1502")
        self.assertGreater(b1601.charges["세대전기료"], b1502.charges["세대전기료"])

    def test_full_settlement_grand_total(self):
        items = [
            CostItem("일반관리비", 3_500_000, AllocationMethod.AREA),
            CostItem("청소비", 1_200_000, AllocationMethod.EQUAL),
            CostItem("승강기유지비", 800_000, AllocationMethod.OCCUPIED),
            CostItem("세대전기료", 1_280_000, AllocationMethod.USAGE),
        ]
        s = settle(self.units, items, self.usage)
        expected = 3_500_000 + 1_200_000 + 800_000 + 1_280_000
        self.assertEqual(s.grand_total, expected)
        self.assertEqual(s.verify(), [])

    def test_empty_units_raises(self):
        with self.assertRaises(ValueError):
            settle([], [CostItem("청소비", 100, AllocationMethod.EQUAL)])


if __name__ == "__main__":
    unittest.main()
