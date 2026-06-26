---
description: Use whenever writing or editing code that calls an exchange / broker / trading API (place, cancel, or query orders; fetch balances or positions). Enforces a resilient call boundary so live-money calls never go out unguarded.
---

# API boundary guard

Every call that crosses the boundary to an exchange or broker is a place where
real money and real failures live. Do NOT write a bare API call. Wrap it.

For each outbound trading API call, the code MUST:

1. **Wrap the call** in try/except (try-catch). Never let an exchange call throw
   uncaught into the trading loop.
2. **Retry transient failures with exponential backoff** — up to **3 attempts**,
   delays roughly `1s, 2s, 4s` (add jitter). Retry only *transient* errors:
   timeouts, 429 rate limits, 5xx, connection resets. Do **not** blindly retry
   business errors like "insufficient balance" or "invalid symbol" — those won't
   fix themselves and a retry can do harm.
3. **Alert on final failure** — after retries are exhausted, send a notification
   (Slack / Telegram / whatever the project already uses) with the operation,
   symbol, parameters (no secrets), and the error. Failures must be loud.
4. **Fail safe, not silent** — return/raise a typed result the caller must
   handle. A failed *place-order* must never be mistaken for a filled order, and
   a failed *cancel* must never be assumed cancelled. When in doubt about order
   state, re-query before acting.
5. **Be idempotent where the API allows it** — pass a client order id /
   `newClientOrderId` so a retry can't create a duplicate order.

Reference pattern (adapt to the project's stack and async style):

```python
async def guarded_call(op_name, fn, *, symbol=None, retries=3, base_delay=1.0):
    last_exc = None
    for attempt in range(retries):
        try:
            return await fn()
        except TransientError as e:        # timeout / 429 / 5xx / conn reset
            last_exc = e
            await asyncio.sleep(base_delay * (2 ** attempt) + random.random() * 0.3)
        except ExchangeError as e:         # business error — do not retry
            await notify(f"[{op_name}] {symbol} failed (no retry): {e}")
            raise
    await notify(f"[{op_name}] {symbol} failed after {retries} attempts: {last_exc}")
    raise OrderBoundaryError(op_name, symbol) from last_exc
```

Before finishing, scan the diff for any exchange call that is **not** routed
through this guard and fix it. If the project has no `notify()` or transient/
business error split yet, propose adding them rather than skipping the safety.
