"""메인 트레이딩 루프.

매 주기마다: 캔들 조회 -> 전략 신호 -> 리스크 평가 -> 주문 실행 -> 기록.
백그라운드 스레드로 돌리며 start()/stop() 으로 제어한다. 웹 대시보드가
이 객체의 status() 를 읽어 표시한다.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from ..config import OrderMode, Settings
from ..exchange.base import ExchangeClient
from ..exchange.factory import create_client
from ..risk.risk_manager import DayState, DecisionType, RiskManager
from ..storage.repositories import TradeRepository
from ..strategies import get_strategy
from ..strategies.base import StrategyContext
from ..strategies.filters import apply_trend_filter
from .order_manager import OrderManager
from .portfolio import Portfolio

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self, settings: Settings, client: ExchangeClient | None = None):
        self.s = settings
        self.access_key = settings.bithumb_access_key
        self.secret_key = settings.bithumb_secret_key
        self.client = client or create_client(
            settings.api_version, self.access_key, self.secret_key
        )
        self.portfolio = Portfolio(cash_krw=settings.base_capital_krw)
        self.order_mgr = OrderManager(
            settings.order_mode,
            settings.fee_rate,
            self.portfolio,
            self.client,
            slippage_pct=settings.slippage_pct,
        )
        self.risk = RiskManager(settings)
        self.strategy = get_strategy(settings.strategy, **settings.strategy_params)

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.running = False
        self.last_price = 0.0
        self.last_action = "대기 중"
        self.last_reason = ""
        self.last_update: datetime | None = None
        self.error: str | None = None

    # ────────────────────── 제어 ──────────────────────
    @property
    def has_keys(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def set_credentials(self, access_key: str, secret_key: str) -> None:
        """대시보드 로그인: 런타임에 API 키를 주입하고 클라이언트를 재생성."""
        if self.running:
            raise RuntimeError("매매 중에는 키를 변경할 수 없습니다. 먼저 정지하세요.")
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.client = create_client(
            self.s.api_version, self.access_key, self.secret_key
        )
        self.order_mgr.client = self.client

    def verify_credentials(self) -> bool:
        """키 유효성 확인 (잔고 조회 시도)."""
        self.client.get_balances()
        return True

    def restore_state(self) -> bool:
        """저장된 포지션 상태를 복구 (재시작 대비). 복구 시 True."""
        st = TradeRepository.load_state(self.s.market, self.s.order_mode.value)
        if not st:
            return False
        self.portfolio.cash_krw = st["cash_krw"]
        self.portfolio.coin_volume = st["coin_volume"]
        self.portfolio.entry_price = st["entry_price"]
        self.portfolio.high_price = st["high_price"]
        self.portfolio.realized_pnl_total = st["realized_pnl_total"]
        self.portfolio.consecutive_losses = st["consecutive_losses"]
        logger.info("이전 상태 복구: 현금 %.0f, 코인 %.6f",
                    self.portfolio.cash_krw, self.portfolio.coin_volume)
        return True

    def start(self) -> None:
        if self.running:
            return
        if self.s.order_mode == OrderMode.LIVE and not self.has_keys:
            raise RuntimeError("live 모드는 API 키가 필요합니다 (로그인 또는 .env).")
        # paper/live 는 재시작 시 이전 포지션 상태를 복구 (백테스트 제외)
        if self.s.order_mode != OrderMode.BACKTEST:
            try:
                self.restore_state()
            except Exception as e:
                logger.warning("상태 복구 실패(무시): %s", e)
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("트레이더 시작 (mode=%s)", self.s.order_mode.value)

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        if self._thread:
            self._thread.join(timeout=self.s.poll_interval_sec + 2)
        logger.info("트레이더 정지")

    # ────────────────────── 루프 ──────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
                self.error = None
            except Exception as e:  # 루프가 죽지 않도록 방어
                self.error = str(e)
                logger.exception("스텝 오류: %s", e)
            self._stop.wait(self.s.poll_interval_sec)

    def step(self) -> None:
        """한 사이클 실행 (테스트/백테스트에서도 재사용)."""
        candles = self.client.get_candles(
            self.s.market, unit=self.s.candle_unit, count=200
        )
        if len(candles) < self.strategy.min_candles():
            self.last_reason = "캔들 데이터 부족"
            return

        price = candles[-1].close
        self.last_price = price
        self.portfolio.mark_price(price)

        # live 모드면 실제 잔고로 동기화
        if self.s.order_mode == OrderMode.LIVE:
            try:
                self.portfolio.sync_from_balances(
                    self.client.get_balances(), self.s.market
                )
            except Exception as e:
                logger.warning("잔고 동기화 실패: %s", e)

        ctx = StrategyContext(
            candles=candles,
            has_position=self.portfolio.has_position,
            entry_price=self.portfolio.entry_price,
        )
        signal = self.strategy.generate_signal(ctx)
        signal = apply_trend_filter(
            signal, [c.close for c in candles], self.s.trend_filter_ma
        )

        day = DayState(
            realized_pnl_today=TradeRepository.realized_pnl_today(
                self.s.order_mode.value
            ),
            consecutive_losses=self.portfolio.consecutive_losses,
            capital=self.portfolio.total_value(price),
        )
        decision = self.risk.evaluate(
            signal, self.portfolio.position_state(), price, day
        )

        self._execute(decision, price)
        self.last_action = decision.type.value
        self.last_reason = decision.reason
        self.last_update = datetime.now(timezone.utc)

        # 자산 스냅샷 기록 + 포지션 상태 영속화 (재시작 복구용)
        TradeRepository.add_equity(
            cash_krw=self.portfolio.cash_krw,
            position_value=self.portfolio.position_value(price),
            total_value=self.portfolio.total_value(price),
            mode=self.s.order_mode.value,
        )
        if self.s.order_mode != OrderMode.BACKTEST:
            TradeRepository.save_state(
                market=self.s.market, mode=self.s.order_mode.value,
                portfolio=self.portfolio,
            )

    def _execute(self, decision, price: float) -> None:
        if decision.type == DecisionType.BUY:
            result = self.order_mgr.buy(self.s.market, decision.krw_amount, price)
            TradeRepository.add_trade(
                market=self.s.market,
                side="buy",
                price=result.price,
                volume=result.volume,
                krw=result.paid_krw,
                fee=result.fee,
                mode=self.s.order_mode.value,
                reason=decision.reason,
            )
            logger.info("매수 %s @ %.2f (%s)", result.volume, result.price, decision.reason)

        elif decision.type == DecisionType.SELL:
            entry = self.portfolio.entry_price
            result = self.order_mgr.sell(self.s.market, decision.volume, price)
            realized = result.paid_krw - entry * result.volume
            TradeRepository.add_trade(
                market=self.s.market,
                side="sell",
                price=result.price,
                volume=result.volume,
                krw=result.paid_krw,
                fee=result.fee,
                mode=self.s.order_mode.value,
                reason=decision.reason,
                realized_pnl=realized,
            )
            logger.info(
                "매도 %s @ %.2f 손익=%.0f (%s)",
                result.volume, result.price, realized, decision.reason,
            )

    # ────────────────────── 상태 ──────────────────────
    def status(self) -> dict:
        price = self.last_price
        return {
            "running": self.running,
            "mode": self.s.order_mode.value,
            "api_version": self.s.api_version,
            "has_keys": self.has_keys,
            "market": self.s.market,
            "strategy": self.s.strategy,
            "last_price": price,
            "cash_krw": round(self.portfolio.cash_krw),
            "coin_volume": self.portfolio.coin_volume,
            "entry_price": self.portfolio.entry_price,
            "position_value": round(self.portfolio.position_value(price)),
            "total_value": round(self.portfolio.total_value(price)),
            "pnl_total": round(
                self.portfolio.total_value(price) - self.s.base_capital_krw
            ),
            "pnl_pct": round(
                (self.portfolio.total_value(price) / self.s.base_capital_krw - 1)
                * 100,
                2,
            )
            if self.s.base_capital_krw
            else 0,
            "last_action": self.last_action,
            "last_reason": self.last_reason,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
        }
