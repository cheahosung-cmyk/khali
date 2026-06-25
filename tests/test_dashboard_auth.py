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


def _client(token, db):
    # Host 헤더 allowlist 통과를 위해 base_url 을 127.0.0.1 로 (TestClient 기본은 testserver)
    return TestClient(_app(token, db), base_url="http://127.0.0.1")


def test_no_token_allows_all():
    with tempfile.TemporaryDirectory() as d:
        c = _client("", os.path.join(d, "a.db"))
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/config").json()["auth_required"] is False


def test_token_blocks_unauthenticated():
    with tempfile.TemporaryDirectory() as d:
        c = _client("secret123", os.path.join(d, "b.db"))
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
        c = _client("secret123", os.path.join(d, "c.db"))
        # 페이지 자체는 열려야 토큰 입력 UI 를 띄울 수 있음
        assert c.get("/").status_code == 200


def test_host_header_allowlist_blocks_dns_rebinding():
    with tempfile.TemporaryDirectory() as d:
        c = _client("", os.path.join(d, "h.db"))
        # 악성 Host(DNS 리바인딩) → 403
        assert c.get("/api/status", headers={"Host": "evil.com"}).status_code == 403
        # 허용된 Host → 통과
        assert c.get("/api/status", headers={"Host": "127.0.0.1"}).status_code == 200


def test_refuse_start_when_exposed_without_token():
    from khali.web.app import create_app
    with tempfile.TemporaryDirectory() as d:
        s = Settings(order_mode=OrderMode.PAPER, engine="single",
                     database_url=f"sqlite:///{os.path.join(d, 'r.db')}",
                     host="0.0.0.0", dashboard_token="")
        with pytest.raises(RuntimeError):
            create_app(s)
