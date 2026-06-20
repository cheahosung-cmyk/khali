"""상가 관리비 정산 엔진 테스트.

표준 라이브러리만으로 실행 가능: `python -m pytest` 또는 `python -m unittest`.
"""

import unittest

from src.calculator import allocate, settle
from src.models import AllocationMethod, CostItem, Unit, round_won


class TestAllocate(unittest.TestCase):
    def test_sum_matches_total_exactly(self):
        weights = {"a": 66.1, "b": 49.5, "c": 99.2}
        result = allocate(1_000_000, weights)
        self.assertEqual(sum(result.values()), 1_000_000)

    def test_equal_weights(self):
        result = allocate(100, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(sum(result.values()), 100)
        self.assertEqual(sorted(result.values()), [33, 33, 34])

    def test_zero_weight_gets_nothing(self):
        result = allocate(1000, {"a": 0, "b": 10, "c": 0})
        self.assertEqual(result["a"], 0)
        self.assertEqual(result["c"], 0)
        self.assertEqual(result["b"], 1000)


class TestRoundWon(unittest.TestCase):
    def test_round_half_up(self):
        self.assertEqual(round_won(100.4), 100)
        self.assertEqual(round_won(100.5), 101)
        self.assertEqual(round_won(165000.0), 165000)


class TestSettle(unittest.TestCase):
    def setUp(self):
        # 5층 상가, 301호 공실
        self.units = [
            Unit("1", "101", 66.1, True, "행복편의점"),
            Unit("1", "102", 49.5, True, "민들레카페"),
            Unit("2", "201", 99.2, True, "튼튼정형외과"),
            Unit("3", "301", 99.2, False, ""),  # 공실
            Unit("4", "401", 99.2, True, "한빛세무회계"),
            Unit("5", "501", 132.3, True, "스카이학원"),
        ]
        self.usage = {
            "1-101": {"호실전기료": 540},
            "1-102": {"호실전기료": 380},
            "2-201": {"호실전기료": 720},
            "3-301": {"호실전기료": 0},
            "4-401": {"호실전기료": 410},
            "5-501": {"호실전기료": 950},
        }

    def test_area_allocation_total_matches(self):
        items = [CostItem("일반관리비", 1_800_000, AllocationMethod.AREA)]
        s = settle(self.units, items, self.usage)
        self.assertEqual(s.item_total_charged("일반관리비"), 1_800_000)
        self.assertEqual(s.verify(), [])

    def test_vacant_share_is_owner_borne(self):
        # 면적 배분 시 공실(301)도 면적분이 산정되며, 그 몫은 건물주 부담으로 분리된다.
        items = [CostItem("일반관리비", 1_800_000, AllocationMethod.AREA)]
        s = settle(self.units, items, self.usage)
        vacant = next(b for b in s.bills if b.unit.key == "3-301")
        self.assertGreater(vacant.supply, 0)  # 공실도 면적분 산정
        self.assertEqual(s.owner_borne_total, vacant.supply)
        # 임차인 청구 + 공실 부담 = 건물 총액
        self.assertEqual(s.supply_billed_total + s.owner_borne_total, 1_800_000)

    def test_usage_vacant_pays_zero(self):
        items = [CostItem("호실전기료", 1_650_000, AllocationMethod.USAGE)]
        s = settle(self.units, items, self.usage)
        vacant = next(b for b in s.bills if b.unit.key == "3-301")
        self.assertEqual(vacant.supply, 0)  # 사용량 0 → 부담 없음
        self.assertEqual(s.item_total_charged("호실전기료"), 1_650_000)

    def test_vat_calculation(self):
        items = [CostItem("일반관리비", 1_000_000, AllocationMethod.EQUAL)]
        s = settle(self.units, items, self.usage, vat_rate=0.1)
        # 임차인 5호실 균등(공실 1호실분은 건물주 부담)
        for bill in s.tenant_bills:
            self.assertEqual(s.vat(bill), round_won(bill.supply * 0.1))
            self.assertEqual(s.billed_total(bill), bill.supply + s.vat(bill))
        self.assertEqual(s.vat_total, sum(s.vat(b) for b in s.tenant_bills))

    def test_no_vat(self):
        items = [CostItem("청소비", 600_000, AllocationMethod.EQUAL)]
        s = settle(self.units, items, self.usage, vat_rate=0.0)
        self.assertEqual(s.vat_total, 0)
        self.assertEqual(s.billed_grand_total, s.supply_billed_total)

    def test_full_settlement_verifies(self):
        items = [
            CostItem("일반관리비", 1_800_000, AllocationMethod.AREA),
            CostItem("청소비", 600_000, AllocationMethod.EQUAL),
            CostItem("호실전기료", 1_650_000, AllocationMethod.USAGE),
        ]
        s = settle(self.units, items, self.usage)
        self.assertEqual(s.building_total, 1_800_000 + 600_000 + 1_650_000)
        self.assertEqual(s.verify(), [])
        # 임차인 청구 + 공실 부담 = 건물 총액
        self.assertEqual(
            s.supply_billed_total + s.owner_borne_total, s.building_total
        )

    def test_empty_units_raises(self):
        with self.assertRaises(ValueError):
            settle([], [CostItem("청소비", 100, AllocationMethod.EQUAL)])


if __name__ == "__main__":
    unittest.main()
