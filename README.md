# Khali — 빗썸 개인용 자동 코인매매 시스템

리플(XRP) 등 빗썸 마켓을 대상으로 하는 **개인용** 자동매매 시스템입니다.
수익률을 지키는 핵심은 리스크 관리라는 원칙 아래, 모든 전략 위에 강제
손절·익절·포지션 사이징·일일 손실 한도 레이어를 둡니다.

> ⚠️ **투자 위험 고지**: 자동매매는 실제 자금 손실 위험이 있습니다. 반드시
> `backtest → paper → live` 순서로 충분히 검증한 뒤, 잃어도 되는 소액으로만
> 시작하세요. 과거 성과가 미래 수익을 보장하지 않습니다.

## 안전 3단계

| 모드 | 설명 | 실제 돈 |
|------|------|:------:|
| `backtest` | 과거 캔들로 전략 수익률·MDD·승률 검증 | ❌ |
| `paper` | 실시간 시세 + 가상 주문 (기본값) | ❌ |
| `live` | 실제 빗썸 주문 실행 | ✅ |

`.env` 의 `ORDER_MODE` 한 곳만 바꿔 전환합니다. 기본값은 `paper` 이라
실수로 돈이 나가지 않습니다.

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # 키/파라미터 편집
```

## 빗썸 API 키 (live 모드만 필요)

빗썸 **API 1.0**(Connect Key + HMAC-SHA512)과 **2.0**(JWT)을 모두 지원합니다.
`.env` 의 `API_VERSION` 으로 선택하며 기본값은 **1**(1.0)입니다.

1. 빗썸 → 마이페이지 → API 관리에서 키 발급
2. **반드시 '자산조회 + 거래' 권한만 부여하고 '출금' 권한은 제외**하세요.
   (본 시스템은 출금 기능을 코드에 아예 구현하지 않습니다.)
3. 키 입력 방법 (둘 중 하나):
   - **대시보드 로그인** — `khali web` 실행 후 화면 상단에서 Key 입력 → 🔑 로그인
     (키는 **메모리에만** 저장, 디스크에 쓰지 않음)
   - **.env 파일** — `BITHUMB_ACCESS_KEY` / `BITHUMB_SECRET_KEY` 입력

## 사용법

```bash
# 1) 백테스트 — 모든 전략 비교
khali backtest --all

# 2) 단일 전략 백테스트
khali backtest

# 3) 웹 대시보드 (기본 명령)
khali web            # http://127.0.0.1:8000

# 4) 헤드리스 매매 루프
khali run
```

설치가 막히는 환경에서는 `PYTHONPATH=src python -m khali.main <명령>` 으로도
실행할 수 있습니다.

## 실데이터 백테스트 결과 (XRP/KRW)

빗썸에서 실제 XRP/KRW 캔들을 받아 측정한 결과입니다. **수익률 우선**이라도
하락장에서 자본을 지키는 것이 곧 수익률임을 보여줍니다.

(수수료 **0.04%** 적용)

**최근 ~7개월 (1시간봉 5000개)** — 이 구간 XRP 자체가 **-48.2%** 하락:

| 전략 | 수익률 | MDD | 거래 | 승률 |
|------|:------:|:---:|:---:|:---:|
| 매수후보유 (벤치마크) | **-48.2%** | - | - | - |
| volatility_breakout | **-0.62%** | 0.6% | 6 | 0% |
| rsi_reversion | -2.22% | 4.8% | 12 | 50% |
| ma_crossover | -4.06% | 4.2% | 16 | 25% |

> 시장이 -48% 폭락하는 동안 전략들은 거의 본전을 지켰습니다(현금 보유로 하락 회피).

**전체 일봉 (2017~2026, 약 9년, 강세장 포함)** — 매수후보유 +425%:

| 전략 | 수익률 | MDD | 거래 | 승률 |
|------|:------:|:---:|:---:|:---:|
| rsi_reversion | **+57.5%** | 9.0% | 34 | 47% |
| volatility_breakout | -0.5% | 7.5% | 10 | 20% |
| ma_crossover | -15.6% | 15.6% | 18 | 22% |

직접 재현:
```bash
khali backtest --all --count 5000              # 1시간봉
CANDLE_UNIT=1440 khali backtest --all --count 5000   # 일봉
```

> ⚠️ 과거 성과가 미래 수익을 보장하지 않습니다. 파라미터(`POSITION_SIZE_PCT`,
> 손절·익절 등)와 캔들 주기를 바꿔가며 충분히 검증한 뒤 paper → live 로 진행하세요.

## 파라미터 최적화

`khali optimize` 는 각 전략의 파라미터 조합을 그리드 서치하고, **과최적화를
막기 위해 학습(70%)/검증(30%) 구간을 분리**해 in-sample뿐 아니라
out-of-sample 성과까지 함께 보여줍니다. 기본 점수는 `calmar`(수익률/MDD).

```bash
khali optimize --all                       # 모든 전략 (1h봉)
CANDLE_UNIT=1440 khali optimize --all       # 일봉 기준
khali optimize --strategy rsi_reversion --metric return
```

**실데이터 일봉(9년) 최적화 결과** — 학습 → 검증(미학습 구간) 일반화 성능:

| 전략 | 최적 파라미터 | 학습 수익 | **검증 수익** | 검증 MDD |
|------|------|:---:|:---:|:---:|
| ma_crossover | `short=15, long=100` | +50.5% | **+25.1%** | 3.0% |
| rsi_reversion | `period=14, oversold=30` | +57.5% | **+10.3%** | 8.2% |
| volatility_breakout | `k=0.8` | +113.2% | +9.4% | 3.5% |

> 변동성돌파 `k=0.8` 은 학습 +113%로 화려하지만 검증 +9.4% — 학습 구간에
> 과최적화된 신호입니다. 반면 **`ma_crossover short=15/long=100` 이 검증 구간에서
> +25%로 가장 안정적인 일반화 성능**을 보였습니다. 학습 성과만 보고 고르면 안 됩니다.

찾은 파라미터는 `.env` 의 `STRATEGY_PARAMS`(JSON)에 넣으면 paper/live 매매에
그대로 적용됩니다:
```bash
STRATEGY=ma_crossover
STRATEGY_PARAMS={"short": 15, "long": 100}
```

## 전략 (플러그인)

| 이름 | 방식 |
|------|------|
| `ma_crossover` | 이동평균 골든/데드크로스 추세추종 |
| `rsi_reversion` | RSI 과매도/과매수 평균회귀 |
| `volatility_breakout` | 변동성 돌파 (래리 윌리엄스, 기본값) |

새 전략은 `src/khali/strategies/` 에 `Strategy` 를 상속하고
`@register("이름")` 만 붙이면 자동 등록됩니다.

## 리스크 파라미터 (`.env`)

| 항목 | 기본값 | 의미 |
|------|:------:|------|
| `POSITION_SIZE_PCT` | 0.5 | 거래당 진입 비중 (자본 대비) |
| `STOP_LOSS_PCT` | 0.02 | 손절선 (-2%) |
| `TAKE_PROFIT_PCT` | 0.04 | 익절선 (+4%) |
| `TRAILING_STOP_PCT` | 0.02 | 트레일링 스탑 (고점 대비 -2%) |
| `DAILY_LOSS_LIMIT_PCT` | 0.1 | 일일 손실 한도 초과 시 당일 중단 |
| `MAX_CONSECUTIVE_LOSSES` | 3 | 연속 손실 N회 후 쿨다운 |
| `MIN_ORDER_KRW` | 5000 | 빗썸 최소 주문 금액 |

## 아키텍처

```
시세(빗썸 API) → 전략 플러그인 → 리스크 매니저 → 주문매니저(모드분기) → DB
                                                          ↘ 웹 대시보드
```

- `exchange/` 빗썸 API 2.0 클라이언트 (JWT 인증, 출금 미구현)
- `strategies/` 전략 플러그인 + 레지스트리
- `risk/` 손절·익절·사이징·한도 강제 레이어
- `engine/` 포트폴리오·주문매니저·메인 루프
- `backtest/` 과거 데이터 시뮬레이터
- `web/` FastAPI 대시보드
- `storage/` SQLAlchemy 거래·자산 기록

## 테스트

```bash
pytest -q
```

## 면책

본 소프트웨어는 개인 사용 목적으로 제공되며, 사용으로 인한 어떠한 금전적
손실에 대해서도 작성자/제공자는 책임지지 않습니다.
