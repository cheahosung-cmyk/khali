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

    # 추세 필터: N봉 이동평균 위일 때만 신규 매수 허용 (0=off).
    # 하락장 매수를 피해 수익률을 지키는 장치.
    trend_filter_ma: int = Field(default=0, alias="TREND_FILTER_MA")
    # 백테스트 슬리피지 (체결 불리 비율, 현실성 보정)
    slippage_pct: float = Field(default=0.0, alias="SLIPPAGE_PCT")

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
    # 엔진 선택: single(단일코인 전략) | rotation(멀티코인 상대강도 로테이션)
    engine: str = Field(default="single", alias="ENGINE")
    # 킬스위치: 평가자산이 고점 대비 이 비율 하락하면 전량청산+정지 (0=off)
    max_drawdown_stop_pct: float = Field(default=0.0, alias="MAX_DRAWDOWN_STOP_PCT")

    # ── 로테이션 엔진 ──
    rotation_basket: str = Field(
        default="BTC,ETH,XRP,SOL,ADA,DOGE,TRX,LINK", alias="ROTATION_BASKET"
    )
    rotation_lookback: int = Field(default=120, alias="ROTATION_LOOKBACK")
    rotation_rebalance_days: int = Field(default=14, alias="ROTATION_REBALANCE_DAYS")
    rotation_regime_ma: int = Field(default=50, alias="ROTATION_REGIME_MA")
    # 보유 코인 개별 손절(진입가 대비). 0=off. 구간검증상 레짐게이트와 중복이라 기본 off,
    # 다른 바스켓/장세용 안전장치로 제공.
    rotation_stop_pct: float = Field(default=0.0, alias="ROTATION_STOP_PCT")

    # ── 자본 투입 사전등록 결정규칙 (forward 리포트가 PASS/FAIL 판정) ──
    # 확증편향 방지: 자본 키우기 전 '미리' 정한 기준. khali report 가 이걸로 판정.
    decision_min_trades: int = Field(default=30, alias="DECISION_MIN_TRADES")
    decision_min_return_pct: float = Field(default=0.0, alias="DECISION_MIN_RETURN_PCT")
    decision_max_dd_pct: float = Field(default=25.0, alias="DECISION_MAX_DD_PCT")

    @property
    def basket_list(self) -> list[str]:
        return [s.strip().upper() for s in self.rotation_basket.split(",") if s.strip()]

    # ── 웹 ──
    host: str = Field(default="127.0.0.1", alias="HOST")
    # 대시보드 접근 토큰. 설정 시 모든 API 호출에 X-Auth-Token 필요.
    # 외부(0.0.0.0) 노출 시 반드시 설정하세요.
    dashboard_token: str = Field(default="", alias="DASHBOARD_TOKEN")
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
