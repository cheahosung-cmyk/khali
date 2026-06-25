"""CLI 진입점.

사용 예:
    python -m khali.main backtest          # 합성 데이터로 백테스트
    python -m khali.main backtest --csv data.csv --symbol 005930
"""

from __future__ import annotations

import argparse

from khali.data import feed
from khali.engine.backtest import run_backtest
from khali.risk.manager import RiskConfig, RiskManager
from khali.strategy.volatility_breakout import VolatilityBreakout


def _backtest(args: argparse.Namespace) -> None:
    if args.csv:
        bars = list(feed.from_csv(args.csv, args.symbol))
    else:
        bars = list(feed.synthetic(args.symbol, days=args.days))

    strategy = VolatilityBreakout(k=args.k, ma_window=args.ma)
    risk = RiskManager(RiskConfig(), args.cash)
    result = run_backtest(bars, strategy, starting_cash=args.cash, risk=risk)

    print(f"전략: {strategy.name}  종목: {args.symbol}  봉: {len(bars)}")
    print(result.summary())


def main() -> None:
    parser = argparse.ArgumentParser(prog="khali", description="한국 주식 자동매매")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="전략 백테스트")
    bt.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    bt.add_argument("--symbol", default="005930", help="종목코드 (기본 삼성전자)")
    bt.add_argument("--days", type=int, default=250)
    bt.add_argument("--cash", type=float, default=10_000_000)
    bt.add_argument("--k", type=float, default=0.5, help="변동성 돌파 계수")
    bt.add_argument("--ma", type=int, default=5, help="추세 필터 이동평균 기간")
    bt.set_defaults(func=_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
