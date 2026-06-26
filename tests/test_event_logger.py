"""로컬 이벤트 로거 테스트 — 파일 기록·포맷(외부 전송 없음)."""

import json

from khali.monitoring.event_logger import EventLogger


def test_writes_jsonl_with_timestamp(tmp_path):
    path = tmp_path / "ev.jsonl"
    log = EventLogger(str(path), console=False)
    log({"type": "rebalance", "allowed": ["005930"]})
    log({"type": "fill", "symbol": "005930", "side": "BUY", "qty": 3,
         "price": 70000, "pnl": 0})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["type"] == "rebalance" and "ts" in rec


def test_format_fill_is_human_readable():
    out = EventLogger._format({"ts": "T", "type": "fill", "symbol": "005930",
                               "side": "SELL", "qty": 2, "price": 71000, "pnl": 1500})
    assert "체결" in out and "005930" in out and "SELL" in out


def test_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "ev.jsonl"
    EventLogger(str(path), console=False)({"type": "x"})
    assert path.exists()
