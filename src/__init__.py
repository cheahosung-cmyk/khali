"""Khali - 관리비 정산 에이전트.

관리소장을 위한 공동주택 관리비 정산 자동화 도구.
세대 정보 / 비용 항목 / 계량기 검침값(CSV)을 입력하면
세대별 고지서를 자동으로 산출한다.
"""

__version__ = "0.1.0"

from .models import Unit, CostItem, AllocationMethod, UnitBill, Settlement
from .calculator import settle, allocate

__all__ = [
    "Unit",
    "CostItem",
    "AllocationMethod",
    "UnitBill",
    "Settlement",
    "settle",
    "allocate",
]
