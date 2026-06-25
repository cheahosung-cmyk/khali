"""forward 성과 리포트 집계 테스트."""

import os
import tempfile

from khali.storage.db import init_db
from khali.storage.repositories import TradeRepository


def test_performance_summary_counts_and_gate():
    with tempfile.TemporaryDirectory() as d:
        init_db(f"sqlite:///{os.path.join(d, 'r.db')}")
        # 매수 2 + 매도 2 (1승 1패), 수수료 기록
        TradeRepository.add_trade(market="KRW-XRP", side="buy", price=1000, volume=10,
                                  krw=10000, fee=4, mode="paper")
        TradeRepository.add_trade(market="KRW-XRP", side="sell", price=1100, volume=10,
                                  krw=11000, fee=4, mode="paper", realized_pnl=992)
        TradeRepository.add_trade(market="KRW-XRP", side="buy", price=1100, volume=9,
                                  krw=9900, fee=4, mode="paper")
        TradeRepository.add_trade(market="KRW-XRP", side="sell", price=1000, volume=9,
                                  krw=9000, fee=4, mode="paper", realized_pnl=-908)
        # 자산 스냅샷 (시장노출 비율·MDD 계산)
        TradeRepository.add_equity(cash_krw=0, position_value=50000, total_value=50000, mode="paper")
        TradeRepository.add_equity(cash_krw=0, position_value=45000, total_value=45000, mode="paper")
        TradeRepository.add_equity(cash_krw=50500, position_value=0, total_value=50500, mode="paper")

        p = TradeRepository.performance_summary("paper")
        assert p["closed_trades"] == 2
        assert p["win_rate_pct"] == 50.0
        assert round(p["net_realized_pnl"]) == 84      # 992 - 908
        assert round(p["total_fees"]) == 16            # 4*4
        assert p["max_drawdown_pct"] >= 9.9            # 50000 -> 45000 = -10%
        assert 60 <= p["time_in_market_pct"] <= 70     # 2/3 스냅샷이 포지션 보유


def test_performance_summary_empty():
    with tempfile.TemporaryDirectory() as d:
        init_db(f"sqlite:///{os.path.join(d, 'e.db')}")
        p = TradeRepository.performance_summary("paper")
        assert p["closed_trades"] == 0
        assert p["days"] == 0
        assert p["time_in_market_pct"] == 0.0
