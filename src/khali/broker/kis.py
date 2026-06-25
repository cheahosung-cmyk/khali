"""한국투자증권(KIS) OpenAPI 실거래 어댑터 — 스켈레톤.

실제 엔드포인트 구조를 반영하되, 네트워크/인증 호출부는 의도적으로
미구현(NotImplementedError)으로 둔다. 키 발급·약관 동의 후 채워야 하며,
페이퍼/백테스트로 충분히 검증되기 전에는 절대 live로 돌리지 않는다.

문서: https://apiportal.koreainvestment.com  (KIS Developers)
- 모의투자 도메인: https://openapivts.koreainvestment.com:29443
- 실전투자 도메인: https://openapi.koreainvestment.com:9443
"""

from __future__ import annotations

from khali.broker.base import Broker
from khali.config import KISConfig
from khali.models import Account, Order


REAL_DOMAIN = "https://openapi.koreainvestment.com:9443"
PAPER_DOMAIN = "https://openapivts.koreainvestment.com:29443"


class KISBroker(Broker):
    """실거래 어댑터. is_paper=True면 KIS 모의투자 서버를 가리킨다.

    구현 시 주의:
    - 접근토큰(OAuth)은 만료(24h)되므로 캐시·자동 갱신 필요
    - 주문 TR_ID가 실전/모의·매수/매도별로 다름
    - 레이트리밋(초당 호출 수) 및 부분체결 처리 필요
    """

    def __init__(self, config: KISConfig):
        self.config = config
        self.domain = PAPER_DOMAIN if config.is_paper else REAL_DOMAIN
        self._token: str | None = None

    # --- 인증 ---
    def _ensure_token(self) -> str:
        """OAuth 접근토큰 발급/갱신. POST /oauth2/tokenP."""
        raise NotImplementedError(
            "KIS OAuth 미구현. 키 발급 후 aiohttp로 /oauth2/tokenP 호출 구현 필요."
        )

    # --- Broker 인터페이스 ---
    def submit(self, order: Order) -> Order:
        """주문 전송. POST /uapi/domestic-stock/v1/trading/order-cash."""
        raise NotImplementedError(
            "실거래 주문 미구현. 페이퍼/백테스트 검증 완료 전 호출 금지."
        )

    def get_account(self) -> Account:
        """잔고 조회. GET /uapi/domestic-stock/v1/trading/inquire-balance."""
        raise NotImplementedError("잔고 조회 미구현.")

    def last_price(self, symbol: str) -> float:
        """현재가 조회. GET /uapi/domestic-stock/v1/quotations/inquire-price."""
        raise NotImplementedError("현재가 조회 미구현.")
