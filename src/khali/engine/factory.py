"""설정에 따라 매매 엔진(single/rotation)을 생성.

두 엔진 모두 start()/stop()/status()/set_credentials()/verify_credentials()
인터페이스를 공유하므로 웹/CLI 가 동일하게 다룬다.
"""

from __future__ import annotations

from ..config import Settings
from .rotation_trader import RotationTrader
from .trader import Trader


def create_engine(settings: Settings, client=None):
    if settings.engine == "rotation":
        return RotationTrader(settings, client)
    return Trader(settings, client)
