"""브로커 인터페이스. 코어는 이 추상 타입에만 의존한다.

paper / kis(실거래) 어댑터가 이를 구현하며, 전략·리스크 코드는 어느
구현인지 알 필요가 없다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from khali.models import Account, Order


class Broker(ABC):
    @abstractmethod
    def submit(self, order: Order) -> Order:
        """주문을 제출하고 체결 결과가 반영된 Order를 반환한다."""

    @abstractmethod
    def get_account(self) -> Account:
        """현재 현금/포지션 스냅샷."""

    @abstractmethod
    def last_price(self, symbol: str) -> float:
        """최근가(평가/사이징용)."""
