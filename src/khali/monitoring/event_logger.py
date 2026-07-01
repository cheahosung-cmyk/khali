"""로컬 이벤트 로거 — 외부 서비스 없이 **컴퓨터에서만** 확인.

LiveSession/live_runner의 on_event 훅에 꽂아 체결·리밸런스·kill-switch 등을
콘솔과 로컬 JSONL 파일에 남긴다. 텔레그램 등 외부 전송은 하지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class EventLogger:
    def __init__(self, path: str = "logs/khali_events.jsonl", console: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.console = console

    def __call__(self, event: dict) -> None:
        record = {"ts": datetime.now().isoformat(timespec="seconds"), **event}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.console:
            print(self._format(record))

    @staticmethod
    def _format(e: dict) -> str:
        ts = e.get("ts", "")
        t = e.get("type")
        if t == "fill":
            return (f"[{ts}] 💱 체결 {e['side']} {e['symbol']} "
                    f"{e['qty']}주 @{e['price']:,.0f}  손익 {e.get('pnl', 0):,.0f}")
        if t == "rebalance":
            return f"[{ts}] 🔄 리밸런스 → {e.get('allowed')}"
        if t == "kill_switch":
            return f"[{ts}] ⛔ KILL-SWITCH 발동 ({e.get('day')})"
        if t == "warmup_done":
            return f"[{ts}] ✅ warmup 완료 ({e.get('bars')}봉)"
        if t == "dry_run":
            return (f"[{ts}] 🧪 dry-run [{e.get('mode')}] "
                    f"의도주문 {e.get('intended_orders')}")
        if t == "executed":
            return (f"[{ts}] 🚀 실행 [{e.get('mode')}] "
                    f"현금 {e.get('cash', 0):,.0f}  보유 {e.get('positions')}")
        return f"[{ts}] {e}"
