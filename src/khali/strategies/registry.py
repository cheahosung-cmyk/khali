"""전략 등록/조회 레지스트리.

@register("name") 데코레이터로 전략 클래스를 등록하고,
get_strategy(name, **params) 로 인스턴스를 만든다.
"""

from __future__ import annotations

from typing import Type

from .base import Strategy

_REGISTRY: dict[str, Type[Strategy]] = {}


def register(name: str):
    def deco(cls: Type[Strategy]) -> Type[Strategy]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get_strategy(name: str, **params) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(
            f"알 수 없는 전략 '{name}'. 사용 가능: {list(_REGISTRY)}"
        )
    return _REGISTRY[name](**params)


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
