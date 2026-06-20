"""Khali CLI 진입점.

사용법:
  khali web                 # 웹 대시보드 실행 (기본)
  khali backtest            # 설정된 전략 백테스트
  khali backtest --all      # 모든 전략 비교 백테스트
  khali run                 # 헤드리스로 매매 루프 실행
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import get_settings


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_web(args) -> None:
    import uvicorn

    from .web.app import create_app

    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)


def cmd_backtest(args) -> None:
    from .backtest.backtester import Backtester
    from .exchange.bithumb_client import BithumbClient
    from .strategies import list_strategies

    settings = get_settings()
    client = BithumbClient()
    print(f"캔들 다운로드: {settings.market} {settings.candle_unit}분봉 x{args.count}")
    candles = client.get_candles(settings.market, settings.candle_unit, args.count)
    client.close()
    print(f"  -> {len(candles)}개 ({candles[0].timestamp} ~ {candles[-1].timestamp})\n")

    bt = Backtester(settings)
    names = list_strategies() if args.all else [settings.strategy]
    results = [bt.run(candles, name) for name in names]
    results.sort(key=lambda r: r.total_return_pct, reverse=True)
    print("=" * 70)
    for r in results:
        print(r.summary())
    print("=" * 70)
    if args.all and results:
        print(f"\n🏆 최고 수익 전략: {results[0].strategy} "
              f"({results[0].total_return_pct:+.2f}%)")


def cmd_run(args) -> None:
    from .engine.trader import Trader
    from .storage.db import init_db

    settings = get_settings()
    init_db(settings.database_url)
    trader = Trader(settings)
    if settings.order_mode.value == "live":
        print("⚠️  LIVE 모드입니다. 실제 주문이 실행됩니다. Ctrl+C 로 중단.")
    trader.start()
    try:
        while True:
            time.sleep(10)
            s = trader.status()
            print(f"[{s['mode']}] {s['market']} {s['last_price']:.1f} | "
                  f"평가 {s['total_value']:,}원 ({s['pnl_pct']:+.2f}%) | "
                  f"{s['last_action']} - {s['last_reason']}")
    except KeyboardInterrupt:
        trader.stop()
        print("\n정지했습니다.")


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="khali", description="빗썸 자동매매 시스템")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("web", help="웹 대시보드 실행")

    bt = sub.add_parser("backtest", help="전략 백테스트")
    bt.add_argument("--all", action="store_true", help="모든 전략 비교")
    bt.add_argument("--count", type=int, default=200, help="캔들 개수 (최대 200)")

    sub.add_parser("run", help="헤드리스 매매 루프")

    args = parser.parse_args()
    command = args.command or "web"
    {"web": cmd_web, "backtest": cmd_backtest, "run": cmd_run}[command](args)


if __name__ == "__main__":
    sys.exit(main())
