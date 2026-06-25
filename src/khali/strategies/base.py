"""전략 플러그인 인터페이스 + 신호 정의."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from ..exchange.models import Candle


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    action: Action
    reason: str = ""
    # 진입 비중(0~1). None 이면 엔진/리스크 매니저 기본값 사용.
    target_weight: float | None = None
    confidence: float = 1.0


@dataclass
class StrategyContext:
    """전략이 의사결정에 쓰는 현재 상태."""

    candles: list[Candle]            # 시간 오름차순
    has_position: bool               # 현재 코인 보유 여부
    entry_price: float = 0.0         # 보유 시 평균 진입가
    extra: dict = field(default_factory=dict)


class Strategy(ABC):
    """모든 전략의 공통 인터페이스.

    파라미터는 생성자에서 받아 self 에 저장하고, generate_signal 에서
    BUY/SELL/HOLD 신호를 반환한다. 리스크 매니저가 이 신호를 받아
    손절/사이징 등을 최종 적용한다.
    """

    name: str = "base"

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def generate_signal(self, ctx: StrategyContext) -> Signal:
        ...

    def min_candles(self) -> int:
        """신호 계산에 필요한 최소 캔들 수."""
        return 50

    @staticmethod
    def param_grid() -> dict[str, list]:
        """최적화 그리드 서치용 파라미터 후보. 기본은 빈 그리드(튜닝 없음)."""
        return {}
