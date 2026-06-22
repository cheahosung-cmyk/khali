"""대시보드 인증 미들웨어 테스트."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from khali.config import OrderMode, Settings


def _app(token, db):
    from khali.web.app import create_app
    s = Settings(order_mode=OrderMode.PAPER, engine="single",
                 database_url=f"sqlite:///{db}", dashboard_token=token)
    return create_app(s)


def test_no_token_allows_all():
    with tempfile.TemporaryDirectory() as d:
        c = TestClient(_app("", os.path.join(d, "a.db")))
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/config").json()["auth_required"] is False


def test_token_blocks_unauthenticated():
    with tempfile.TemporaryDirectory() as d:
        c = TestClient(_app("secret123", os.path.join(d, "b.db")))
        # 토큰 없이 보호 엔드포인트 → 401
        assert c.get("/api/status").status_code == 401
        assert c.post("/api/start").status_code == 401
        # config 는 토큰 없이도 접근 (인증 필요 여부 안내)
        assert c.get("/api/config").json()["auth_required"] is True
        # 올바른 토큰 → 200
        assert c.get("/api/status", headers={"X-Auth-Token": "secret123"}).status_code == 200
        # 잘못된 토큰 → 401
        assert c.get("/api/status", headers={"X-Auth-Token": "wrong"}).status_code == 401


def test_index_page_open_without_token():
    with tempfile.TemporaryDirectory() as d:
        c = TestClient(_app("secret123", os.path.join(d, "c.db")))
        # 페이지 자체는 열려야 토큰 입력 UI 를 띄울 수 있음
        assert c.get("/").status_code == 200
