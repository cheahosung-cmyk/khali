"""환경설정 로딩 (.env -> pydantic Settings).

모든 런타임 파라미터는 여기서 한 곳으로 모읍니다. 실거래(live) 전환은
ORDER_MODE 한 곳만 바꾸면 되도록 설계했습니다.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrderMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,  # 테스트에서 필드명으로 직접 생성 허용
    )

    # ── 빗썸 API 키 ──
    # API 1.0: connect key / secret key, API 2.0: access key / secret key
    api_version: int = Field(default=1, alias="API_VERSION")
    bithumb_access_key: str = Field(default="", alias="BITHUMB_ACCESS_KEY")
    bithumb_secret_key: str = Field(default="", alias="BITHUMB_SECRET_KEY")

    # ── 거래 모드 / 대상 ──
    order_mode: OrderMode = Field(default=OrderMode.PAPER, alias="ORDER_MODE")
    market: str = Field(default="KRW-XRP", alias="MARKET")
    base_capital_krw: float = Field(default=50000, alias="BASE_CAPITAL_KRW")
    strategy: str = Field(default="volatility_breakout", alias="STRATEGY")
    # 최적화로 찾은 전략 파라미터 (JSON). 예: {"short": 15, "long": 100}
    strategy_params_json: str = Field(default="", alias="STRATEGY_PARAMS")
    candle_unit: int = Field(default=60, alias="CANDLE_UNIT")

    # ── 리스크 관리 ──
    position_size_pct: float = Field(default=0.5, alias="POSITION_SIZE_PCT")
    stop_loss_pct: float = Field(default=0.02, alias="STOP_LOSS_PCT")
    take_profit_pct: float = Field(default=0.04, alias="TAKE_PROFIT_PCT")
    trailing_stop_pct: float = Field(default=0.02, alias="TRAILING_STOP_PCT")
    daily_loss_limit_pct: float = Field(default=0.1, alias="DAILY_LOSS_LIMIT_PCT")
    max_consecutive_losses: int = Field(default=3, alias="MAX_CONSECUTIVE_LOSSES")
    min_order_krw: float = Field(default=5000, alias="MIN_ORDER_KRW")
    fee_rate: float = Field(default=0.0004, alias="FEE_RATE")

    # ── 엔진 ──
    poll_interval_sec: int = Field(default=10, alias="POLL_INTERVAL_SEC")

    # ── 웹 ──
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # ── DB ──
    database_url: str = Field(
        default="sqlite:///./data/khali.db", alias="DATABASE_URL"
    )

    # ── 텔레그램 (선택) ──
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    @property
    def strategy_params(self) -> dict:
        if not self.strategy_params_json.strip():
            return {}
        import json

        try:
            return json.loads(self.strategy_params_json)
        except json.JSONDecodeError:
            return {}

    @property
    def has_api_keys(self) -> bool:
        return bool(self.bithumb_access_key and self.bithumb_secret_key)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
