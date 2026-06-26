"""CLI 진입점.

사용 예:
    python -m khali.main backtest          # 합성 데이터로 백테스트
    python -m khali.main backtest --csv data.csv --symbol 005930
"""

from __future__ import annotations

import argparse

from collections import defaultdict

from khali.broker.paper import PaperBroker
from khali.data import feed
from khali.engine.backtest import run_backtest
from khali.engine.live import LiveSession
from khali.risk.manager import RiskConfig, RiskManager
from khali.strategy.trend_breakout import TrendBreakout
from khali.strategy.volatility_breakout import VolatilityBreakout

# 기본 유니버스 (대형주). 페이퍼 데모용.
DEFAULT_UNIVERSE = [
    "005930", "000660", "035420", "005380", "051910",
    "035720", "006400", "105560", "207940", "012330",
]


def _backtest(args: argparse.Namespace) -> None:
    if args.naver:
        bars = feed.from_naver(args.symbol, args.start, args.end)
    elif args.csv:
        bars = list(feed.from_csv(args.csv, args.symbol))
    else:
        bars = list(feed.synthetic(args.symbol, days=args.days))

    strategy = VolatilityBreakout(k=args.k, ma_window=args.ma)
    risk = RiskManager(RiskConfig(), args.cash)
    result = run_backtest(bars, strategy, starting_cash=args.cash, risk=risk)

    print(f"전략: {strategy.name}  종목: {args.symbol}  봉: {len(bars)}")
    print(result.summary())


def _paper(args: argparse.Namespace) -> None:
    """페이퍼(모의) 실시간 루프 데모.

    네이버 실데이터를 받아 앞부분은 warmup, 최근 `ticks`일을 '라이브 틱'으로
    하루씩 흘려 LiveSession을 구동한다. 같은 코드가 KISBroker로 교체되면
    그대로 실거래(모의투자)가 된다.
    """
    data = {s: feed.from_naver(s, args.start, args.end) for s in DEFAULT_UNIVERSE}
    data = {s: b for s, b in data.items() if b}

    # 최근 ticks일을 라이브로, 그 이전을 warmup으로 분리
    split = {s: b[:-args.ticks] for s, b in data.items()}
    live = {s: b[-args.ticks:] for s, b in data.items()}

    broker = PaperBroker(args.cash)
    risk = RiskManager(RiskConfig(), args.cash)
    session = LiveSession(
        broker,
        lambda: TrendBreakout(k=args.k, ma_window=20, atr_window=14, trail_mult=2.5),
        risk, list(data.keys()),
        lookback=120, top_n=3, rebalance_days=20,
        on_event=lambda e: print("  ·", e),
    )
    session.warmup(split)

    # 라이브 틱을 날짜별로 묶어 하루씩 step
    by_date: dict = defaultdict(dict)
    for sym, bars in live.items():
        for b in bars:
            by_date[b.ts.date()][sym] = b
    print(f"=== 페이퍼 실시간 루프 ({len(by_date)}일) ===")
    for date in sorted(by_date):
        print(f"[{date}]")
        session.step(by_date[date])

    ret = session.equity / args.cash - 1
    print(f"\n최종 평가자본 {session.equity:,.0f}  수익률 {ret:+.2%}  "
          f"거래 {session.result.trades}회")


def _live(args: argparse.Namespace) -> None:
    """KIS 모의/실거래 라이브 1회 실행 (매 거래일 장 마감 후 호출 상정)."""
    from khali.config import KISConfig
    from khali.engine.live_runner import run_once

    try:
        config = KISConfig.from_env()
    except RuntimeError as e:
        print(f"⚠️  {e}")
        print("config/.env.example를 복사해 .env에 KIS 키를 채우세요.")
        return

    mode = "모의투자" if config.is_paper else "⚠️ 실전투자"
    action = "주문 실행" if args.execute else "dry-run(주문 미제출)"
    print(f"=== KIS 라이브 [{mode}] — {action} ===")
    try:
        run_once(config, execute=args.execute, allow_live=args.allow_live)
    except RuntimeError as e:
        print(f"⛔ {e}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="khali", description="한국 주식 자동매매")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="전략 백테스트")
    bt.add_argument("--naver", action="store_true", help="네이버 금융 실데이터 사용")
    bt.add_argument("--start", default="20240101", help="실데이터 시작 YYYYMMDD")
    bt.add_argument("--end", default="20260625", help="실데이터 종료 YYYYMMDD")
    bt.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    bt.add_argument("--symbol", default="005930", help="종목코드 (기본 삼성전자)")
    bt.add_argument("--days", type=int, default=250)
    bt.add_argument("--cash", type=float, default=10_000_000)
    bt.add_argument("--k", type=float, default=0.5, help="변동성 돌파 계수")
    bt.add_argument("--ma", type=int, default=5, help="추세 필터 이동평균 기간")
    bt.set_defaults(func=_backtest)

    pp = sub.add_parser("paper", help="페이퍼(모의) 실시간 루프 데모")
    pp.add_argument("--start", default="20240101", help="데이터 시작 YYYYMMDD")
    pp.add_argument("--end", default="20260625", help="데이터 종료 YYYYMMDD")
    pp.add_argument("--ticks", type=int, default=20, help="라이브로 흘릴 최근 거래일 수")
    pp.add_argument("--cash", type=float, default=10_000_000)
    pp.add_argument("--k", type=float, default=0.5, help="변동성 돌파 계수")
    pp.set_defaults(func=_paper)

    lv = sub.add_parser("live", help="KIS 모의/실거래 1회 실행 (.env 키 필요)")
    lv.add_argument("--execute", action="store_true",
                    help="실제 주문 제출 (기본은 dry-run, 주문 미제출)")
    lv.add_argument("--allow-live", action="store_true",
                    help="실전 계좌 주문 허용 (모의 검증 후에만!)")
    lv.set_defaults(func=_live)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
