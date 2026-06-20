"""전략 플러그인 패키지.

import 시 기본 전략들을 registry 에 자동 등록한다.
"""

from .base import Action, Signal, Strategy  # noqa: F401
from .registry import get_strategy, list_strategies, register  # noqa: F401

# 기본 전략 모듈을 임포트하면 데코레이터가 registry 에 등록한다.
from . import ma_crossover  # noqa: F401,E402
from . import rsi_reversion  # noqa: F401,E402
from . import volatility_breakout  # noqa: F401,E402
