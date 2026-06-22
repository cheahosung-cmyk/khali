"""FastAPI 앱 + 대시보드 API.

엔드포인트:
  GET  /                 대시보드 HTML
  GET  /api/status       현재 트레이더 상태 (잔고/수익률/포지션)
  GET  /api/trades       최근 거래 내역
  GET  /api/equity       자산 추이
  POST /api/start        매매 시작
  POST /api/stop         매매 정지
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..engine.factory import create_engine
from ..storage.db import init_db
from ..storage.repositories import TradeRepository

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


class LoginPayload(BaseModel):
    access_key: str
    secret_key: str
    verify: bool = True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_db(settings.database_url)

    trader = create_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        trader.stop()

    app = FastAPI(title="Khali 빗썸 자동매매", lifespan=lifespan)
    app.state.trader = trader

    if settings.host == "0.0.0.0" and not settings.dashboard_token:
        logger.warning(
            "⚠️ 대시보드가 0.0.0.0(외부)에 노출되는데 DASHBOARD_TOKEN 이 없습니다! "
            "누구나 키 입력·봇 조작 가능. .env 에 DASHBOARD_TOKEN 을 설정하세요."
        )

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        # 토큰이 설정된 경우에만 /api/* 보호 (대시보드 페이지는 열려서 토큰 입력 가능)
        path = request.url.path
        if (
            settings.dashboard_token
            and path.startswith("/api/")
            and path != "/api/config"   # 인증 필요 여부 안내용 (토큰 전 접근)
        ):
            if request.headers.get("X-Auth-Token") != settings.dashboard_token:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/api/config")
    def config() -> dict:
        return {"auth_required": bool(settings.dashboard_token), "engine": settings.engine}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status() -> dict:
        return trader.status()

    @app.get("/api/trades")
    def trades(limit: int = 50) -> list[dict]:
        return TradeRepository.recent_trades(limit)

    @app.get("/api/equity")
    def equity() -> list[dict]:
        return TradeRepository.equity_curve()

    @app.post("/api/login")
    def login(payload: LoginPayload) -> dict:
        """API 키를 런타임에 주입(메모리 저장). 디스크에 쓰지 않습니다."""
        try:
            trader.set_credentials(payload.access_key, payload.secret_key)
            if payload.verify:
                trader.verify_credentials()
            return {"ok": True, "has_keys": trader.has_keys}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/logout")
    def logout() -> dict:
        if trader.running:
            return {"ok": False, "error": "매매 중에는 로그아웃 불가"}
        trader.set_credentials("", "")
        return {"ok": True, "has_keys": False}

    @app.post("/api/start")
    def start() -> dict:
        try:
            trader.start()
            return {"ok": True, "running": trader.running}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/stop")
    def stop() -> dict:
        trader.stop()
        return {"ok": True, "running": trader.running}

    return app
