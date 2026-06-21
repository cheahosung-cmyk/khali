"""API 버전에 맞는 거래소 클라이언트 생성."""

from __future__ import annotations

from .base import ExchangeClient
from .bithumb_client import BithumbClient
from .bithumb_v1 import BithumbV1Client


def create_client(
    api_version: int, access_key: str = "", secret_key: str = ""
) -> ExchangeClient:
    if api_version == 1:
        return BithumbV1Client(access_key, secret_key)
    return BithumbClient(access_key, secret_key)
