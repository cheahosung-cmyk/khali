"""거래소 클라이언트 공통 인터페이스.

엔진/백테스터는 이 인터페이스에만 의존하므로 빗썸 API 1.0 / 2.0 을
자유롭게 교체할 수 있다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Balance, Candle, OrderResult, Ticker


class ExchangeClient(ABC):
    # ── 공개: 시세 ──
    @abstractmethod
    def get_candles(self, market: str, unit: int = 60, count: int = 200) -> list[Candle]:
        ...

    @abstractmethod
    def get_ticker(self, market: str) -> Ticker:
        ...

    # ── 비공개: 계좌/주문 ──
    @abstractmethod
    def get_balances(self) -> list[Balance]:
        ...

    @abstractmethod
    def execute_buy(self, market: str, krw_amount: float, ref_price: float) -> OrderResult:
        """시장가 매수. ref_price 는 수량 환산/체결가 추정용 참고가."""
        ...

    @abstractmethod
    def execute_sell(self, market: str, volume: float, ref_price: float) -> OrderResult:
        """시장가 매도."""
        ...

    def close(self) -> None:  # pragma: no cover - 선택 구현
        pass
