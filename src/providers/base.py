"""Provider 인터페이스."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class Provider(abc.ABC):
    """모든 LLM provider 의 공통 인터페이스.

    Attributes:
        model: 사용할 모델명
    """

    model: str

    #: provider 식별용 이름 (서브클래스에서 재정의)
    vendor: str = "base"

    #: 실제 외부 API 를 호출하는지 여부 (mock=False)
    is_live: bool = False

    @abc.abstractmethod
    def complete(self, system: str, user: str) -> str:
        """system / user 프롬프트를 받아 응답 텍스트를 반환한다.

        Args:
            system: 시스템(역할) 프롬프트
            user: 사용자 프롬프트

        Returns:
            모델이 생성한 텍스트
        """
        raise NotImplementedError

    @property
    def label(self) -> str:
        """`vendor:model` 형태의 라벨."""
        return f"{self.vendor}:{self.model}"
