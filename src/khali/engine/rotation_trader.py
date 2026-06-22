"""멀티코인 상대강도 로테이션 자동매매 엔진 (paper/live).

20인 토론 결정 방향을 실거래 엔진으로 구현. RotationBacktester 와 동일한
규칙을 실시간으로 적용한다:
  - BTC 일봉 레짐이 약세면 전액 현금 (즉시 청산)
  - 강세면 바스켓 중 상대강도(모멘텀) 1위 코인 보유
  - rebalance_days 마다 재선정, 그 사이엔 레짐 악화/킬스위치만 감시
  - 모든 전환에 수수료+슬리피지 반영 (순수익 기준)

한 번에 한 코인만 보유하므로 Portfolio(단일코인 모델)를 그대로 쓴다.
held_symbol 로 현재 보유 코인을 추적하고 DB에 영속화(재시작 복구)한다.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from ..config import OrderMode, Settings
from ..exchange.base import ExchangeClient
from ..exchange.factory import create_client
from ..notify.telegram import TelegramNotifier
from ..storage.repositories import TradeRepository
from ..strategies.indicators import sma
from .order_manager import OrderManager
from .portfolio import Portfolio

logger = logging.getLogger(__name__)


class RotationTrader:
    def __init__(self, settings: Settings, client: ExchangeClient | None = None):
        self.s = settings
        self.access_key = settings.bithumb_access_key
        self.secret_key = settings.bithumb_secret_key
        self.client = client or create_client(
            settings.api_version, self.access_key, self.secret_key
        )
        self.portfolio = Portfolio(cash_krw=settings.base_capital_krw)
        self.order_mgr = OrderManager(
            settings.order_mode, settings.fee_rate, self.portfolio,
            self.client, slippage_pct=settings.slippage_pct,
        )
        self.held_symbol: str | None = None
        self.last_rebalance: datetime | None = None
        self.peak_equity = settings.base_capital_krw
        self.killed = False
        # status() 가 네트워크 없이 읽도록 루프에서 갱신하는 캐시
        self.last_equity = settings.base_capital_krw
        self.last_price = 0.0
        self.notifier = TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        self.prev_regime: str | None = None
        self._error_notified = False

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.running = False
        self.regime = "?"
        self.last_action = "대기 중"
        self.last_reason = ""
        self.last_update: datetime | None = None
        self.error: str | None = None

    # ────────────────────── 제어 ──────────────────────
    @property
    def has_keys(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def set_credentials(self, access_key: str, secret_key: str) -> None:
        if self.running:
            raise RuntimeError("매매 중에는 키를 변경할 수 없습니다.")
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.client = create_client(self.s.api_version, self.access_key, self.secret_key)
        self.order_mgr.client = self.client

    def verify_credentials(self) -> bool:
        self.client.get_balances()
        return True

    def restore_state(self) -> bool:
        st = TradeRepository.load_state_by_mode(self.s.order_mode.value)
        if not st:
            return False
        self.portfolio.cash_krw = st["cash_krw"]
        self.portfolio.coin_volume = st["coin_volume"]
        self.portfolio.entry_price = st["entry_price"]
        self.portfolio.high_price = st["high_price"]
        self.portfolio.realized_pnl_total = st["realized_pnl_total"]
        self.portfolio.consecutive_losses = st["consecutive_losses"]
        self.held_symbol = st["market"] if st["market"] not in ("CASH", "") else None
        logger.info("로테이션 상태 복구: 보유=%s 현금=%.0f", self.held_symbol, self.portfolio.cash_krw)
        return True

    def start(self) -> None:
        if self.running:
            return
        if self.s.order_mode == OrderMode.LIVE and not self.has_keys:
            raise RuntimeError("live 모드는 API 키가 필요합니다.")
        self.killed = False
        if self.s.order_mode != OrderMode.BACKTEST:
            try:
                self.restore_state()
            except Exception as e:
                logger.warning("상태 복구 실패(무시): %s", e)
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("로테이션 엔진 시작 (mode=%s)", self.s.order_mode.value)

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        if self._thread:
            self._thread.join(timeout=self.s.poll_interval_sec + 2)

    # ────────────────────── 루프 ──────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
                self.error = None
                self._error_notified = False
            except Exception as e:
                self.error = str(e)
                logger.exception("로테이션 스텝 오류: %s", e)
                if not self._error_notified:   # 에러는 한 번만 알림 (스팸 방지)
                    self.notifier.send(f"⚠️ Khali 로테이션 오류: {e}")
                    self._error_notified = True
            self._stop.wait(self.s.poll_interval_sec)

    def _price(self, symbol: str) -> float:
        return self.client.get_ticker(f"KRW-{symbol}").trade_price

    def _btc_bull(self) -> bool:
        candles = self.client.get_candles("KRW-BTC", 1440, 200)
        closes = [c.close for c in candles]
        ma = sma(closes, self.s.rotation_regime_ma)
        return ma is not None and closes[-1] > ma

    def _rank_top(self) -> str | None:
        """백테스트(RotationBacktester)와 동일한 lookback 순수 모멘텀으로 1위 선정.

        과거에는 score_market(고정 30일+MA복합)을 썼으나, 백테스트가 검증한
        rotation_lookback 모멘텀과 신호가 달라 정합성 결함이 있었다. 이제 일치시킨다.
        """
        lookback = self.s.rotation_lookback
        best, best_mom = None, float("-inf")
        for sym in self.s.basket_list:
            try:
                closes = [c.close for c in self.client.get_candles(f"KRW-{sym}", 1440, lookback + 5)]
                if len(closes) < lookback + 1:
                    continue
                mom = closes[-1] / closes[-1 - lookback] - 1   # lookback일 모멘텀
                if mom > best_mom:
                    best, best_mom = sym, mom
            except Exception:
                continue
        return best

    def _equity(self) -> float:
        if self.held_symbol and self.portfolio.has_position:
            self.last_price = self._price(self.held_symbol)
            return self.portfolio.cash_krw + self.portfolio.coin_volume * self.last_price
        self.last_price = 0.0
        return self.portfolio.cash_krw

    def _reconcile_live(self) -> None:
        """live: 거래소 실제 잔고를 단일 진실원천으로 동기화 (부분체결 대응)."""
        if self.s.order_mode != OrderMode.LIVE:
            return
        balances = self.client.get_balances()
        krw = next((b for b in balances if b.currency == "KRW"), None)
        if krw:
            self.portfolio.cash_krw = krw.total
        if self.held_symbol:
            coin = next((b for b in balances if b.currency == self.held_symbol), None)
            self.portfolio.coin_volume = coin.total if coin else 0.0
            # 실제 보유 수량이 0이면(외부 매도/미체결) 보유 해제
            if not self.portfolio.has_position:
                self.held_symbol = None
                self.portfolio.entry_price = 0.0

    def _go_cash(self, reason: str) -> None:
        if self.held_symbol and self.portfolio.has_position:
            price = self._price(self.held_symbol)
            entry = self.portfolio.entry_price
            vol = self.portfolio.coin_volume
            res = self.order_mgr.sell(f"KRW-{self.held_symbol}", vol, price)
            realized = res.paid_krw - entry * res.volume
            self._record("sell", self.held_symbol, res.price, res.volume, realized, reason)
        self.held_symbol = None

    def _enter(self, symbol: str, reason: str) -> None:
        price = self._price(symbol)
        krw = self.portfolio.cash_krw
        if krw < self.s.min_order_krw:
            self.last_action, self.last_reason = "hold", f"현금 부족({krw:.0f}원)"
            return
        res = self.order_mgr.buy(f"KRW-{symbol}", krw, price)
        # 체결 검증: 체결수량 0이면 보유로 간주하지 않음 (미체결/거부)
        if res.volume <= 0:
            self.last_action, self.last_reason = "hold", f"{symbol} 주문 미체결"
            self.notifier.send(f"⚠️ Khali {symbol} 매수 미체결 — 보유 안 함")
            return
        self.held_symbol = symbol
        self._record("buy", symbol, res.price, res.volume, 0.0, reason)

    def step(self) -> None:
        if self.killed:
            self.last_reason = "킬스위치 발동됨 — 정지 상태"
            return

        # 0) live: 거래소 실제 잔고와 동기화 (부분체결/외부거래 반영)
        self._reconcile_live()

        # 1) 킬스위치: 평가자산이 고점 대비 큰 폭 하락하면 전량청산+정지
        equity = self._equity()
        self.peak_equity = max(self.peak_equity, equity)
        if self.s.max_drawdown_stop_pct > 0 and self.peak_equity > 0:
            dd = (equity - self.peak_equity) / self.peak_equity
            if dd <= -abs(self.s.max_drawdown_stop_pct):
                self._go_cash(f"킬스위치: 고점대비 {dd:.1%} 하락")
                self.killed = True
                self.running = False
                self._stop.set()
                self.last_action = "kill"
                self.notifier.send(
                    f"⛔ Khali 킬스위치 발동! 고점대비 {dd:.1%} 하락 → 전량청산·정지. "
                    f"평가자산 {equity:,.0f}원"
                )
                self._persist(equity)
                return

        # 2) 레짐 체크 (매 스텝): 베어면 즉시 현금
        bull = self._btc_bull()
        self.regime = "bull" if bull else "bear"
        if self.prev_regime and self.prev_regime != self.regime:
            self.notifier.send(
                f"📊 Khali BTC 레짐 전환: {self.prev_regime} → {self.regime}"
                + (" (매수 우호적!)" if bull else " (현금 회피)")
            )
        self.prev_regime = self.regime
        if not bull:
            if self.held_symbol:
                self._go_cash("BTC 레짐 약세 → 현금 회피")
            else:
                self.last_action, self.last_reason = "hold", "BTC 약세 — 현금 대기"
            self.last_update = datetime.now(timezone.utc)
            self._persist(self._equity())
            return

        # 3) 리밸런스 시점인지 (강세장에서만 코인 재선정)
        now = datetime.now(timezone.utc)
        due = (
            self.last_rebalance is None
            or (now - self.last_rebalance).days >= self.s.rotation_rebalance_days
        )
        if due:
            top = self._rank_top()
            if top and top != self.held_symbol:
                if self.held_symbol:
                    self._go_cash(f"로테이션: {self.held_symbol}→{top}")
                self._enter(top, f"상대강도 1위 {top}")
            elif not self.held_symbol and top:
                self._enter(top, f"진입: 상대강도 1위 {top}")
            else:
                self.last_action, self.last_reason = "hold", f"보유 유지 {self.held_symbol}"
            self.last_rebalance = now
        else:
            self.last_action, self.last_reason = "hold", f"보유 유지 {self.held_symbol}"

        self.last_update = now
        self._persist(self._equity())

    # ────────────────────── 기록/상태 ──────────────────────
    def _record(
        self, side: str, symbol: str, price: float, volume: float,
        realized: float, reason: str,
    ) -> None:
        TradeRepository.add_trade(
            market=f"KRW-{symbol}", side=side, price=price, volume=volume,
            krw=price * volume, fee=0, mode=self.s.order_mode.value,
            reason=reason, realized_pnl=realized,
        )
        self.last_action, self.last_reason = side, reason
        logger.info("%s %s vol=%.6f @ %.2f 손익=%.0f (%s)",
                    side, symbol, volume, price, realized, reason)
        emoji = "🟢 매수" if side == "buy" else "🔴 매도"
        pnl = f" 손익 {realized:+,.0f}원" if side == "sell" else ""
        self.notifier.send(
            f"{emoji} {symbol} {volume:.4f}개 @ {price:,.0f}원{pnl}\n사유: {reason} "
            f"[{self.s.order_mode.value}]"
        )

    def _persist(self, equity: float) -> None:
        self.last_equity = equity   # status() 캐시 갱신
        TradeRepository.add_equity(
            cash_krw=self.portfolio.cash_krw,
            position_value=equity - self.portfolio.cash_krw,
            total_value=equity, mode=self.s.order_mode.value,
        )
        if self.s.order_mode != OrderMode.BACKTEST:
            # held_symbol 을 market 필드에 저장 (보유 코인 추적)
            TradeRepository.save_state(
                market=self.held_symbol or "CASH",
                mode=self.s.order_mode.value, portfolio=self.portfolio,
            )

    def status(self) -> dict:
        # 캐시된 값만 사용 (웹 요청에서 네트워크 호출 금지)
        equity = self.last_equity
        return {
            "running": self.running,
            "mode": self.s.order_mode.value,
            "engine": "rotation",
            "api_version": self.s.api_version,
            "has_keys": self.has_keys,
            "market": self.held_symbol or "CASH",
            "strategy": f"rotation({self.s.rotation_lookback}d)",
            "regime": self.regime,
            "killed": self.killed,
            "last_price": self.last_price,
            "cash_krw": round(self.portfolio.cash_krw),
            "coin_volume": self.portfolio.coin_volume,
            "total_value": round(equity),
            "pnl_total": round(equity - self.s.base_capital_krw),
            "pnl_pct": round((equity / self.s.base_capital_krw - 1) * 100, 2)
            if self.s.base_capital_krw else 0,
            "last_action": self.last_action,
            "last_reason": self.last_reason,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
        }
