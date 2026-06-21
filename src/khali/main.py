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
    from .exchange.factory import create_client
    from .strategies import list_strategies

    settings = get_settings()
    client = create_client(settings.api_version)  # 시세는 키 불필요
    print(
        f"캔들 다운로드: {settings.market} {settings.candle_unit}분봉 "
        f"x{args.count} (API {settings.api_version}.0)"
    )
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


def cmd_optimize(args) -> None:
    from .backtest.optimizer import Optimizer
    from .exchange.factory import create_client
    from .strategies import list_strategies

    settings = get_settings()
    client = create_client(settings.api_version)
    candles = client.get_candles(settings.market, settings.candle_unit, args.count)
    client.close()
    print(
        f"\n{settings.market} {settings.candle_unit}분봉 {len(candles)}개 | "
        f"지표={args.metric} | 학습:검증 = {int(args.train*100)}:{100-int(args.train*100)}"
    )

    names = list_strategies() if args.all else [args.strategy or settings.strategy]
    opt = Optimizer(settings)
    for name in names:
        rep = opt.optimize(
            candles, name, metric=args.metric, train_ratio=args.train
        )
        if rep.best is None:
            continue
        print(f"\n{'='*78}\n[{name}] 조합 {rep.n_combos}개 탐색 "
              f"(학습 {rep.train_size} / 검증 {rep.test_size}봉)")
        print(f"  {'파라미터':<34} {'학습수익':>8} {'학습MDD':>7} "
              f"{'검증수익':>8} {'검증MDD':>7} {'거래':>4}")
        for r in rep.top:
            p = ", ".join(f"{k}={v}" for k, v in r.params.items()) or "(기본)"
            print(f"  {p:<34} {r.train.total_return_pct:>7.2f}% "
                  f"{r.train.max_drawdown_pct:>6.1f}% "
                  f"{r.test.total_return_pct:>7.2f}% "
                  f"{r.test.max_drawdown_pct:>6.1f}% {r.test.num_trades:>4}")
        b = rep.best
        bp = ", ".join(f"{k}={v}" for k, v in b.params.items()) or "(기본)"
        gen = "✅ 견고" if b.test.total_return_pct > 0 else "⚠️ 검증구간 부진(과최적화 의심)"
        print(f"\n  🏆 최적: {bp}")
        print(f"     학습 {b.train.total_return_pct:+.2f}% → "
              f"검증 {b.test.total_return_pct:+.2f}%  {gen}")


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
    bt.add_argument(
        "--count", type=int, default=2000,
        help="사용할 캔들 개수 (API 1.0 최대 ~5000, 2.0 최대 200)",
    )

    op = sub.add_parser("optimize", help="전략 파라미터 최적화 (그리드 서치)")
    op.add_argument("--strategy", help="대상 전략 (생략 시 .env STRATEGY)")
    op.add_argument("--all", action="store_true", help="모든 전략 최적화")
    op.add_argument("--metric", choices=["calmar", "return"], default="calmar",
                    help="정렬 지표 (기본 calmar: 수익률/MDD)")
    op.add_argument("--train", type=float, default=0.7, help="학습 구간 비율")
    op.add_argument("--count", type=int, default=5000, help="사용할 캔들 개수")

    sub.add_parser("run", help="헤드리스 매매 루프")

    args = parser.parse_args()
    command = args.command or "web"
    {
        "web": cmd_web,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "run": cmd_run,
    }[command](args)


if __name__ == "__main__":
    sys.exit(main())
