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

## 빗썸 API 키 발급 (live 모드만 필요)

1. 빗썸 → 마이페이지 → API 관리에서 키 발급
2. **반드시 '자산조회 + 거래' 권한만 부여하고 '출금' 권한은 제외**하세요.
   (본 시스템은 출금 기능을 코드에 아예 구현하지 않습니다.)
3. 발급한 `access_key` / `secret_key` 를 `.env` 에 입력

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
