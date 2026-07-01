"""전략 인터페이스. 모든 전략은 시세 흐름을 받아 Signal 목록을 낸다."""

from __future__ import annotations

from abc import ABC, abstractmethod

from khali.models import Bar, Position, Signal


class Strategy(ABC):
    """백테스트 / 페이퍼 / 실거래에서 동일하게 쓰이는 전략 베이스.

    상태(이동평균 윈도우 등)는 전략 내부에 보관하되, 봉을 받을 때마다
    `on_bar`로 갱신한다. 외부에서 미래 데이터를 주지 않으므로 룩어헤드
    바이어스가 구조적으로 차단된다.
    """

    name: str = "base"

    @abstractmethod
    def on_bar(self, bar: Bar, position: Position) -> list[Signal]:
        """새 봉 1개를 받아 0개 이상의 신호를 반환한다."""
        raise NotImplementedError

    def warmup(self) -> int:
        """신호를 내기 전에 필요한 최소 봉 개수."""
        return 0
