"""간단한 요청 레이트리미터 (API 차단 방지).

빗썸 공개/사설 API 호출 사이 최소 간격을 강제한다. 스레드 안전.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, min_interval_sec: float = 0.12):
        self.min_interval = min_interval_sec
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()
