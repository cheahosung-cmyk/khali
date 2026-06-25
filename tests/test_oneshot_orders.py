"""수동 단발 주문(buyonce/sellonce) 안전장치 테스트."""

import types

from khali import main as m
from khali.config import OrderMode, Settings


class _Args:
    def __init__(self, **kw):
        self.market = kw.get("market")
        self.krw = kw.get("krw")
        self.volume = kw.get("volume")
        self.yes = kw.get("yes", False)


def test_buyonce_paper_places_no_order(monkeypatch, capsys):
    monkeypatch.setattr(m, "get_settings",
                        lambda: Settings(order_mode=OrderMode.PAPER, market="KRW-XRP"))
    # create_client 가 호출되면 실패시켜, 호출 안 됨을 보장
    import khali.exchange.factory as fac
    monkeypatch.setattr(fac, "create_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("주문경로 진입 금지")))
    m.cmd_buyonce(_Args(krw=6000, yes=True))
    out = capsys.readouterr().out
    assert "live 에서만" in out


def test_buyonce_live_without_keys_refuses(monkeypatch, capsys):
    monkeypatch.setattr(m, "get_settings",
                        lambda: Settings(order_mode=OrderMode.LIVE, market="KRW-XRP",
                                         bithumb_access_key="", bithumb_secret_key=""))
    m.cmd_buyonce(_Args(krw=6000, yes=True))
    assert "API 키가 없습니다" in capsys.readouterr().out


def test_buyonce_live_requires_yes(monkeypatch, capsys):
    captured = {}

    class FakeClient:
        def get_ticker(self, market):
            return types.SimpleNamespace(trade_price=1700.0)
        def execute_buy(self, *a, **k):
            captured["bought"] = True
        def close(self):
            pass

    monkeypatch.setattr(m, "get_settings",
                        lambda: Settings(order_mode=OrderMode.LIVE, market="KRW-XRP",
                                         bithumb_access_key="k", bithumb_secret_key="s",
                                         min_order_krw=5000, base_capital_krw=50000))
    import khali.exchange.factory as fac
    monkeypatch.setattr(fac, "create_client", lambda *a, **k: FakeClient())
    m.cmd_buyonce(_Args(krw=6000, yes=False))   # --yes 없음
    out = capsys.readouterr().out
    assert "--yes" in out
    assert "bought" not in captured           # 주문 실행 안 됨
