"""멀티코인 상대강도 로테이션 백테스터.

20인 토론에서 결정된 방향: 단일 코인 고정 대신, 주기적으로 상대강도가 가장
강한 코인으로 갈아타되, BTC 시장 레짐이 약세면 현금 보유.

- 선택 신호: lookback 기간 수익률(모멘텀) 상위 N
- 레짐 게이트: BTC 종가 > BTC MA(period) 일 때만 알트 보유, 아니면 전액 현금
- 비용: 갈아탈 때(턴오버)만 수수료 + 슬리피지 차감
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings
from ..exchange.models import Candle


@dataclass
class RotationResult:
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    n_rebalances: int
    cash_ratio_pct: float          # 현금 보유 기간 비율
    equity_curve: list[float] = field(default_factory=list)
    holdings_log: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"수익률 {self.total_return_pct:+.2f}% | MDD {self.max_drawdown_pct:.1f}% | "
            f"리밸런스 {self.n_rebalances}회 | 현금보유기간 {self.cash_ratio_pct:.0f}%"
        )


def _date_map(candles: list[Candle]) -> dict:
    return {c.timestamp.date(): c.close for c in candles}


class RotationBacktester:
    def __init__(self, settings: Settings):
        self.s = settings

    def run(
        self,
        candles_by_symbol: dict[str, list[Candle]],
        btc_candles: list[Candle],
        lookback: int = 30,
        rebalance_days: int = 7,
        regime_ma: int = 50,
        use_regime: bool = True,
    ) -> RotationResult:
        symbols = list(candles_by_symbol)
        price_maps = {s: _date_map(c) for s, c in candles_by_symbol.items()}
        btc_map = _date_map(btc_candles)
        btc_closes = [c.close for c in btc_candles]
        btc_dates = [c.timestamp.date() for c in btc_candles]

        # 모든 코인 공통 날짜 (교집합), 정렬
        common = set.intersection(*[set(m) for m in price_maps.values()])
        common &= set(btc_map)
        dates = sorted(common)
        if len(dates) < lookback + rebalance_days + 1:
            raise ValueError("데이터가 부족합니다.")

        cash = self.s.base_capital_krw
        held: str | None = None
        units = 0.0
        cost = (self.s.fee_rate + self.s.slippage_pct)

        equity: list[float] = []
        peak = cash
        max_dd = 0.0
        rebalances = 0
        cash_days = 0
        holdings: list[str] = []

        # BTC MA 조회용: 날짜 -> 인덱스
        btc_idx = {d: i for i, d in enumerate(btc_dates)}

        def btc_bull(d) -> bool:
            i = btc_idx.get(d)
            if i is None or i < regime_ma:
                return False
            ma = sum(btc_closes[i - regime_ma + 1 : i + 1]) / regime_ma
            return btc_closes[i] > ma

        def momentum(sym: str, d, prev_d) -> float:
            p0 = price_maps[sym].get(prev_d)
            p1 = price_maps[sym].get(d)
            if not p0 or not p1:
                return -1e9
            return p1 / p0 - 1

        start = lookback
        for k in range(start, len(dates)):
            d = dates[k]
            # 현재 보유 평가
            cur_price = price_maps[held].get(d) if held else None
            value = cash + (units * cur_price if held and cur_price else 0.0)

            # 리밸런스 시점인가
            if (k - start) % rebalance_days == 0:
                prev_d = dates[k - lookback]
                bull = btc_bull(d) if use_regime else True
                if not bull:
                    target = None  # 현금
                else:
                    ranked = sorted(symbols, key=lambda s: momentum(s, d, prev_d), reverse=True)
                    target = ranked[0]

                if target != held:
                    # 청산
                    if held and cur_price:
                        cash += units * cur_price * (1 - cost)
                        units = 0.0
                        held = None
                    # 신규 진입
                    if target:
                        tp = price_maps[target].get(d)
                        if tp:
                            units = (cash * (1 - cost)) / tp
                            cash = 0.0
                            held = target
                    rebalances += 1
                value = cash + (units * (price_maps[held].get(d) if held else 0) if held else 0.0)

            if held is None:
                cash_days += 1
            holdings.append(held or "CASH")
            equity.append(value)
            peak = max(peak, value)
            if peak:
                max_dd = min(max_dd, (value - peak) / peak * 100)

        final = equity[-1] if equity else self.s.base_capital_krw
        return RotationResult(
            final_value=final,
            total_return_pct=(final / self.s.base_capital_krw - 1) * 100,
            max_drawdown_pct=abs(max_dd),
            n_rebalances=rebalances,
            cash_ratio_pct=cash_days / len(equity) * 100 if equity else 0.0,
            equity_curve=equity,
            holdings_log=holdings,
        )
