"""설정 로더. API 키는 환경변수(.env)에서만 읽으며 절대 커밋하지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str          # 계좌번호 (앞 8자리)
    account_product: str = "01"  # 상품코드 (뒤 2자리)
    is_paper: bool = True    # 기본은 모의투자. 실전은 명시적으로만.

    @classmethod
    def from_env(cls) -> "KISConfig":
        try:
            return cls(
                app_key=os.environ["KIS_APP_KEY"],
                app_secret=os.environ["KIS_APP_SECRET"],
                account_no=os.environ["KIS_ACCOUNT_NO"],
                account_product=os.environ.get("KIS_ACCOUNT_PRODUCT", "01"),
                is_paper=os.environ.get("KIS_IS_PAPER", "true").lower() != "false",
            )
        except KeyError as e:
            raise RuntimeError(
                f"환경변수 {e} 누락. config/.env.example를 참고해 .env를 설정하세요."
            ) from e
