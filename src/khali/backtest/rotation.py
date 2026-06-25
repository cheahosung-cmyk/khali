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
        top_n: int = 1,
        stop_pct: float = 0.0,
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
        holdings_units: dict[str, float] = {}   # symbol -> units (동시 N개 보유)
        entry_px: dict[str, float] = {}         # symbol -> 진입가 (개별 손절용)
        cost = (self.s.fee_rate + self.s.slippage_pct)

        equity: list[float] = []
        peak = cash
        max_dd = 0.0
        rebalances = 0
        cash_days = 0
        holdings: list[str] = []

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

        def portfolio_value(d) -> float:
            return cash + sum(u * price_maps[s][d] for s, u in holdings_units.items())

        start = lookback
        for k in range(start, len(dates)):
            d = dates[k]

            # 개별코인 손절 (매일 검사): 진입가 대비 stop_pct 하락 시 현금화
            if stop_pct > 0:
                for s in list(holdings_units):
                    px = price_maps[s][d]
                    if entry_px.get(s) and px <= entry_px[s] * (1 - stop_pct):
                        cash += holdings_units[s] * px * (1 - cost)
                        del holdings_units[s]
                        entry_px.pop(s, None)

            if (k - start) % rebalance_days == 0:
                prev_d = dates[k - lookback]
                bull = btc_bull(d) if use_regime else True
                targets = []
                if bull:
                    ranked = sorted(symbols, key=lambda s: momentum(s, d, prev_d), reverse=True)
                    targets = ranked[:top_n]
                equity_now = portfolio_value(d)
                target_val = (equity_now / len(targets)) if targets else 0.0

                # 1) 타깃에서 빠진 코인 전량 매도
                for s in list(holdings_units):
                    if s not in targets:
                        cash += holdings_units[s] * price_maps[s][d] * (1 - cost)
                        del holdings_units[s]
                        entry_px.pop(s, None)
                        rebalances += 1
                # 2) 과보유분 매도 (균등비중 초과)
                for s in targets:
                    cur_val = holdings_units.get(s, 0.0) * price_maps[s][d]
                    if cur_val > target_val:
                        sell_units = (cur_val - target_val) / price_maps[s][d]
                        cash += sell_units * price_maps[s][d] * (1 - cost)
                        holdings_units[s] -= sell_units
                        rebalances += 1
                # 3) 부족분 매수 (현금 한도 내)
                for s in targets:
                    cur_val = holdings_units.get(s, 0.0) * price_maps[s][d]
                    if cur_val < target_val:
                        spend = min(target_val - cur_val, cash)
                        if spend > 0:
                            holdings_units[s] = holdings_units.get(s, 0.0) + spend * (1 - cost) / price_maps[s][d]
                            cash -= spend
                            entry_px.setdefault(s, price_maps[s][d])   # 신규 진입가 기록
                            rebalances += 1

            if not holdings_units:
                cash_days += 1
            holdings.append("+".join(sorted(holdings_units)) or "CASH")
            value = portfolio_value(d)
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
