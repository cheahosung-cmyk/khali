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
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from ..config import Settings, get_settings
from ..engine.trader import Trader
from ..storage.db import init_db
from ..storage.repositories import TradeRepository

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_db(settings.database_url)

    app = FastAPI(title="Khali 빗썸 자동매매")
    trader = Trader(settings)
    app.state.trader = trader

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

    @app.on_event("shutdown")
    def _shutdown() -> None:
        trader.stop()

    return app
