---
description: Use before running a trading bot against a live/real-money account, or when reviewing order-execution, position, or risk code. Checks for the mistakes that lose real money.
---

# Trade safety review

Before any trading code touches a live account, review it specifically for
money-losing failure modes. This is stricter than a normal code review.

Check, with `file:line` for each finding:

- **Live vs. test isolation** — is there a hard, explicit switch between testnet/
  paper and live? Default to testnet. Tests and backtests must **never** hit a
  live endpoint or place real orders. Live trading requires an unmistakable
  opt-in (env flag + log line on startup).
- **Order correctness** — side, quantity, and price are what the strategy
  intended; quantities respect the exchange's min size / step size / tick size;
  no off-by-one or unit mix-up (base vs. quote, lots vs. units).
- **Idempotency & duplicates** — client order ids prevent a retry from
  double-submitting. A crash-and-restart can't re-fire orders it already sent.
- **State reconciliation** — on startup and after any error, the bot re-queries
  open orders and positions from the exchange instead of trusting local memory.
- **Risk limits** — max position size, max order notional, and a kill switch
  exist and are enforced *before* sending an order, not after.
- **Numerics** — money/quantity use `Decimal` (or integer minor units), never
  binary `float`. No accumulation of float rounding error in PnL or balances.
- **Rate limits & timeouts** — every exchange call has a timeout and respects
  the venue's rate limits; bursts are throttled.
- **Secrets** — API keys come from env/secret store, never hardcoded or logged.
  Keys used here are trade-enabled — confirm withdrawal permission is OFF.
- **Failure visibility** — failures alert loudly (see `api-boundary-guard`); a
  silent exception must not look like success.

Report findings as a prioritized list (blockers first). Be explicit that going
live is the user's decision and they are responsible for testing on testnet
first — this review is not financial advice.
