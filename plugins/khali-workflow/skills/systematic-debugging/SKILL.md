---
description: Use when something is broken, a test fails, or behavior is unexpected. Debug by hypothesis and isolation instead of guessing, to avoid burning effort on random changes.
---

# Systematic debugging

When something fails, do NOT spray speculative fixes. Diagnose first.

Apply the **three-strike rule**: if two changes in a row don't move you closer
to the cause, stop editing and go back to investigation — you're guessing.

The loop:

1. **Reproduce** reliably. Get the exact error, stack trace, and the smallest
   input that triggers it. An intermittent bug you can't reproduce isn't ready
   to fix.
2. **Form one hypothesis** about the cause, stated precisely ("X is null
   because Y runs before Z").
3. **Isolate** — design the cheapest observation (a log, a breakpoint, a unit
   test, a bisect) that would confirm or kill that hypothesis. Run it.
4. **Confirm the root cause** before changing code. Don't fix a symptom.
5. **Make the minimal change** that addresses the root cause, then verify the
   original reproduction is gone and no test regressed.

Prefer reading and instrumenting over rewriting. Add a regression test that
fails before your fix and passes after. State the actual root cause in your
summary — not just "fixed it."
