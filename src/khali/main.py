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
        if args.risk:
            rep = opt.optimize_risk(
                candles, name, strategy_params=settings.strategy_params,
                metric=args.metric, train_ratio=args.train,
            )
        else:
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


def cmd_walkforward(args) -> None:
    from .backtest.walkforward import WalkForward
    from .exchange.factory import create_client
    from .strategies import list_strategies

    settings = get_settings()
    client = create_client(settings.api_version)
    candles = client.get_candles(settings.market, settings.candle_unit, args.count)
    client.close()
    print(f"\n{settings.market} {settings.candle_unit}분봉 {len(candles)}개 | "
          f"워크포워드 학습 {args.train_size} / 검증 {args.test_size}봉 | 지표={args.metric}")

    names = list_strategies() if args.all else [args.strategy or settings.strategy]
    wf = WalkForward(settings)
    for name in names:
        rep = wf.run(candles, name, args.train_size, args.test_size, args.metric)
        print(f"\n{'='*78}\n{rep.summary()}")
        print(f"  {'구간':>2} {'검증시작':>12} {'~검증끝':>12} "
              f"{'최적파라미터':<26} {'검증수익':>8} {'거래':>4}")
        for f in rep.folds:
            p = ", ".join(f"{k}={v}" for k, v in f.best_params.items()) or "(기본)"
            print(f"  {f.index:>2} {f.test_start:>12} {f.test_end:>12} "
                  f"{p:<26} {f.test_return_pct:>7.2f}% {f.test_trades:>4}")


def cmd_check(args) -> None:
    """실거래 연결 self-check: 주문은 절대 내지 않고 시세/인증/잔고만 확인."""
    from .exchange.factory import create_client

    settings = get_settings()
    print(f"API {settings.api_version}.0 | {settings.market} | mode={settings.order_mode.value}")
    client = create_client(
        settings.api_version, settings.bithumb_access_key, settings.bithumb_secret_key
    )
    ok = True
    try:
        t = client.get_ticker(settings.market)
        print(f"  ✅ 공개 시세 OK: 현재가 {t.trade_price:,.0f}원")
    except Exception as e:
        ok = False
        print(f"  ❌ 시세 조회 실패: {e}")

    if not settings.has_api_keys:
        print("  ⚠️  API 키 미설정 → 인증/잔고 확인 건너뜀 (paper 모드는 키 불필요)")
    else:
        try:
            balances = client.get_balances()
            krw = next((b for b in balances if b.currency == "KRW"), None)
            print(f"  ✅ 인증/잔고 OK: 보유 자산 {len(balances)}종"
                  + (f", KRW {krw.total:,.0f}원" if krw else ""))
        except Exception as e:
            ok = False
            print(f"  ❌ 인증/잔고 실패 (키/권한 확인): {e}")
    client.close()
    print("  → 주문은 실행하지 않았습니다 (안전 점검 전용).")
    if not ok:
        raise SystemExit(1)


def cmd_regime(args) -> None:
    """현재 시장 추세(레짐) 진단 — 지금이 매수 우위 장세인지 판단 보조."""
    from .exchange.factory import create_client
    from .strategies.indicators import sma

    settings = get_settings()
    client = create_client(settings.api_version)
    daily = client.get_candles(settings.market, 1440, 200)
    client.close()
    closes = [c.close for c in daily]
    price = closes[-1]
    ma50 = sma(closes, 50)
    ma200 = sma(closes, 200) if len(closes) >= 200 else None

    print(f"\n{settings.market} 현재가 {price:,.0f}원")
    if ma50:
        print(f"  MA50  {ma50:,.0f}원 → 가격이 {'위 ▲' if price > ma50 else '아래 ▼'}")
    if ma200:
        print(f"  MA200 {ma200:,.0f}원 → 가격이 {'위 ▲' if price > ma200 else '아래 ▼'}")

    bull = ma50 and ma200 and price > ma50 > ma200
    bear = ma50 and ma200 and price < ma50 < ma200
    if bull:
        verdict = "🟢 상승 추세 — 롱 전략에 우호적. paper로 검증 후 소액 live 고려"
    elif bear:
        verdict = "🔴 하락 추세 — 롱 전용 전략은 수익 어려움. 현금 보유/대기 권장"
    else:
        verdict = "🟡 횡보/혼조 — 신중히. 변동성돌파로 작게, 손절 엄격히"
    print(f"\n  진단: {verdict}")


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

    op = sub.add_parser("optimize", help="전략/리스크 파라미터 최적화 (그리드 서치)")
    op.add_argument("--strategy", help="대상 전략 (생략 시 .env STRATEGY)")
    op.add_argument("--all", action="store_true", help="모든 전략 최적화")
    op.add_argument("--risk", action="store_true", help="전략 대신 리스크 파라미터 최적화")
    op.add_argument("--metric", choices=["calmar", "return"], default="calmar",
                    help="정렬 지표 (기본 calmar: 수익률/MDD)")
    op.add_argument("--train", type=float, default=0.7, help="학습 구간 비율")
    op.add_argument("--count", type=int, default=5000, help="사용할 캔들 개수")

    wf = sub.add_parser("walkforward", help="워크포워드 분석 (구간별 재최적화)")
    wf.add_argument("--strategy", help="대상 전략 (생략 시 .env STRATEGY)")
    wf.add_argument("--all", action="store_true", help="모든 전략")
    wf.add_argument("--metric", choices=["calmar", "return"], default="calmar")
    wf.add_argument("--train-size", type=int, default=400, help="학습 윈도우 봉 수")
    wf.add_argument("--test-size", type=int, default=120, help="검증 윈도우 봉 수")
    wf.add_argument("--count", type=int, default=5000, help="사용할 캔들 개수")

    sub.add_parser("check", help="실거래 연결 self-check (주문 없음)")
    sub.add_parser("regime", help="현재 시장 추세 진단 (매수 우위 장세인지)")
    sub.add_parser("run", help="헤드리스 매매 루프")

    args = parser.parse_args()
    command = args.command or "web"
    {
        "web": cmd_web,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "walkforward": cmd_walkforward,
        "check": cmd_check,
        "regime": cmd_regime,
        "run": cmd_run,
    }[command](args)


if __name__ == "__main__":
    sys.exit(main())
