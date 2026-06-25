"""빗썸 API 1.0 클라이언트 오프라인 단위 테스트 (네트워크 불필요)."""

from khali.exchange.bithumb_v1 import _INTERVAL_MAP, BithumbV1Client, _to_pair
from khali.exchange.factory import create_client


def test_to_pair_conversions():
    assert _to_pair("KRW-XRP") == ("XRP", "KRW")
    assert _to_pair("XRP_KRW") == ("XRP", "KRW")
    assert _to_pair("BTC") == ("BTC", "KRW")


def test_interval_map_has_common_units():
    assert _INTERVAL_MAP[60] == "1h"
    assert _INTERVAL_MAP[1440] == "24h"
    assert _INTERVAL_MAP[1] == "1m"


def test_signature_is_deterministic_base64():
    c = BithumbV1Client("mykey", "mysecret")
    params = {"endpoint": "/info/balance", "currency": "XRP"}
    sig1 = c._signature("/info/balance", params, "1700000000000")
    sig2 = c._signature("/info/balance", params, "1700000000000")
    assert sig1 == sig2                 # 동일 입력 -> 동일 서명
    assert isinstance(sig1, str) and len(sig1) > 0
    # 다른 nonce -> 다른 서명
    assert c._signature("/info/balance", params, "1700000000001") != sig1


def test_private_call_requires_keys():
    c = BithumbV1Client()  # 키 없음
    try:
        c._private_post("/info/balance", {"currency": "XRP"})
        assert False, "키 없이 호출 시 예외가 발생해야 함"
    except Exception as e:
        assert "키" in str(e)


def test_parse_contracts_weighted_avg_and_fee():
    detail = {"status": "0000", "data": {"contract": [
        {"units": "10", "price": "1700", "fee": "6.8"},
        {"units": "5", "price": "1710", "fee": "3.4"},
    ]}}
    units, avg, fee = BithumbV1Client._parse_contracts(detail)
    assert units == 15
    assert abs(avg - (10 * 1700 + 5 * 1710) / 15) < 1e-6
    assert abs(fee - 10.2) < 1e-9


def test_parse_contracts_empty():
    assert BithumbV1Client._parse_contracts({"data": {}}) == (0.0, 0.0, 0.0)
    assert BithumbV1Client._parse_contracts({}) == (0.0, 0.0, 0.0)


def test_factory_selects_version():
    from khali.exchange.bithumb_client import BithumbClient

    assert isinstance(create_client(1), BithumbV1Client)
    assert isinstance(create_client(2), BithumbClient)
