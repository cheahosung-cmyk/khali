---
description: Use when iterating on a backtest or strategy simulation until it runs cleanly and all tests pass. Structures the run-fix-rerun loop so it converges instead of thrashing.
---

# Backtest iteration loop

When getting a backtest or simulation green, run a disciplined loop rather than
random edits. Pairs well with Claude Code's built-in `/loop` for hands-off
iteration.

Each cycle:

1. **Run** the backtest / test suite and capture the full output — the failing
   assertion or exception, not just "it failed."
2. **Diagnose** one failure at a time using the `systematic-debugging`
   approach: one hypothesis, cheapest check, confirm root cause.
3. **Fix minimally** — change only what the diagnosed cause requires.
4. **Re-run** and confirm that failure is gone and nothing else regressed.
5. Repeat until the suite is fully green.

Guardrails so the loop actually converges:

- **Three-strike rule** — if two cycles pass without reducing failures, stop and
  re-investigate; you're guessing, and on a long loop that just burns tokens.
- **Don't fit the strategy to the data** — making a backtest "pass" by tuning
  parameters to one historical window is overfitting, not a fix. Keep a holdout
  / out-of-sample period.
- **Backtest realism** — account for fees, slippage, and latency; avoid
  look-ahead bias (no future data leaking into a decision) and survivorship
  bias. A backtest that ignores these lies about profitability.
- **Determinism** — seed any randomness so failures are reproducible.

When using `/loop`, give it a clear terminal condition ("until the full backtest
suite passes") and let it run; review the diff and the safety implications
before trusting the result.
