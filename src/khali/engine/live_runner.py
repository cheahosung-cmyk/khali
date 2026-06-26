"""KIS 모의/실거래 라이브 러너.

환경변수의 KIS 키로 KISBroker를 만들고, 일봉을 KIS에서 직접 수급해 warmup한
뒤 '오늘' 봉으로 한 번 의사결정한다. 일봉 전략이므로 운영은 '매 거래일 장
마감 후 1회 실행'(예: cron) 형태가 자연스럽다.

안전 원칙(실거래 가능 코드):
- 실전 계좌(is_paper=False)는 호출자가 명시적으로 허용해야 한다.
- 기본은 dry-run(주문 미제출)으로 '오늘 무엇을 할지'만 보여준다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from khali.broker.kis import KISBroker
from khali.config import KISConfig
from khali.engine.live import LiveSession
from khali.models import Bar
from khali.risk.manager import RiskConfig, RiskManager
from khali.strategy.base import Strategy
from khali.strategy.trend_breakout import TrendBreakout

DEFAULT_UNIVERSE = [
    "005930", "000660", "035420", "005380", "051910",
    "035720", "006400", "105560", "207940", "012330",
]


def default_strategy_factory() -> Callable[[], Strategy]:
    return lambda: TrendBreakout(k=0.5, ma_window=20, atr_window=14, trail_mult=2.5)


def build_session(
    config: KISConfig,
    universe: list[str] | None = None,
    strategy_factory: Callable[[], Strategy] | None = None,
    risk_config: RiskConfig | None = None,
    warmup_days: int = 140,
    lookback: int = 60,
    top_n: int = 3,
    rebalance_days: int = 20,
    on_event: Callable[[dict], None] | None = None,
    today: datetime | None = None,
) -> tuple[LiveSession, dict[str, Bar]]:
    """KISBroker 기반 LiveSession을 구성하고 warmup한다.

    각 종목의 KIS 일봉을 받아 마지막 봉을 '오늘'(step 대상)로, 그 이전을
    warmup으로 분리한다. (KIS 일봉은 1회 호출 ~100봉 제한이 있어 warmup_days는
    보수적으로 둔다. lookback도 그에 맞춰 60으로 기본 설정.)

    반환: (세션, 오늘 봉 dict)
    """
    universe = universe or DEFAULT_UNIVERSE
    strategy_factory = strategy_factory or default_strategy_factory()
    risk_config = risk_config or RiskConfig()

    broker = KISBroker(config)
    risk = RiskManager(risk_config, broker.get_account().cash)
    session = LiveSession(
        broker, strategy_factory, risk, universe,
        lookback=lookback, top_n=top_n, rebalance_days=rebalance_days,
        on_event=on_event,
    )

    today = today or datetime.now()
    start = (today - timedelta(days=warmup_days * 2)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    history: dict[str, list[Bar]] = {}
    today_bars: dict[str, Bar] = {}
    for sym in universe:
        bars = broker.daily_bars(sym, start, end)
        if not bars:
            continue
        history[sym] = bars[:-1]
        today_bars[sym] = bars[-1]

    session.warmup(history)
    return session, today_bars


def run_once(
    config: KISConfig | None = None,
    execute: bool = False,
    allow_live: bool = False,
    on_event: Callable[[dict], None] | None = None,
    **kwargs,
) -> LiveSession:
    """1회 실행(매 거래일 1번 호출 상정).

    execute=False(기본): dry-run — 산출 주문만 출력, 제출하지 않음.
    execute=True: 실제 주문 제출. 단, 실전 계좌는 allow_live=True여야 한다.
    """
    config = config or KISConfig.from_env()

    if execute and not config.is_paper and not allow_live:
        raise RuntimeError(
            "실전 계좌(is_paper=False)에서 주문 실행은 allow_live=True 명시가 "
            "필요합니다. 먼저 모의투자(KIS_IS_PAPER=true)로 충분히 검증하세요."
        )

    log = on_event or (lambda e: print("  ·", e))
    session, today_bars = build_session(config, on_event=log, **kwargs)

    if not execute:
        intents = session.preview(today_bars)
        log({"type": "dry_run", "mode": "paper" if config.is_paper else "real",
             "intended_orders": intents})
    else:
        session.step(today_bars)
        acct = session.broker.get_account()
        log({"type": "executed", "mode": "paper" if config.is_paper else "real",
             "cash": acct.cash, "positions": list(acct.positions)})
    return session
