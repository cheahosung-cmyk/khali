"""킬스위치 고점·리밸런스 영속(재시작 복구) + SQLite 마이그레이션 테스트."""

import os
import tempfile

from sqlalchemy import create_engine, text

from khali.config import OrderMode, Settings
from khali.engine.portfolio import Portfolio
from khali.storage.db import init_db
from khali.storage.repositories import TradeRepository


def test_peak_and_last_rebalance_persist_and_restore():
    from datetime import datetime, timezone
    from khali.engine.rotation_trader import RotationTrader

    with tempfile.TemporaryDirectory() as d:
        db = f"sqlite:///{os.path.join(d, 'p.db')}"
        init_db(db)
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        pf = Portfolio(cash_krw=80000)
        TradeRepository.save_state(market="CASH", mode="paper", portfolio=pf,
                                   peak_equity=120000, last_rebalance=when)
        st = TradeRepository.load_state_by_mode("paper")
        assert st["peak_equity"] == 120000
        assert st["last_rebalance"].replace(tzinfo=timezone.utc) == when

        # 엔진 재시작 시 peak 가 복구되어 킬스위치가 무장해제되지 않음
        s = Settings(api_version=1, order_mode=OrderMode.PAPER, engine="rotation",
                     base_capital_krw=50000, database_url=db)

        class _C:  # 잔고/시세 불필요 (현금 상태)
            def get_balances(self): return []
        t = RotationTrader(s, client=_C())
        t.restore_state()
        # 복구 peak(120000)이 현재 평가자산(80000)보다 크므로 유지 → 고점 기억
        assert t.peak_equity == 120000
        assert t.last_rebalance is not None


def test_sqlite_migration_adds_missing_columns():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "old.db")
        # 구버전 스키마: peak_equity / last_rebalance 컬럼 없음
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as c:
            c.execute(text(
                "CREATE TABLE bot_state (id INTEGER PRIMARY KEY, market TEXT, mode TEXT, "
                "cash_krw FLOAT, coin_volume FLOAT, entry_price FLOAT, high_price FLOAT, "
                "realized_pnl_total FLOAT, consecutive_losses INTEGER, updated_at DATETIME)"
            ))
            c.execute(text("INSERT INTO bot_state (id, market, mode, cash_krw, coin_volume, "
                           "entry_price, high_price, realized_pnl_total, consecutive_losses) "
                           "VALUES (1,'CASH','paper',50000,0,0,0,0,0)"))
        eng.dispose()
        # init_db 가 누락 컬럼을 안전하게 추가해야 함 (크래시 없이)
        init_db(f"sqlite:///{path}")
        st = TradeRepository.load_state_by_mode("paper")
        assert st is not None
        assert st["peak_equity"] == 0.0          # 추가된 컬럼 기본값
        assert st["last_rebalance"] is None
