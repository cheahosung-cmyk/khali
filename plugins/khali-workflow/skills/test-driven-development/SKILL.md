---
description: Use when implementing new behavior or fixing a bug that can be covered by a test. Drive the change with a failing test first (RED-GREEN-REFACTOR).
---

# Test-driven development

Write the test before the implementation. This pins down the intended behavior
and maximizes first-try correctness.

Follow the RED → GREEN → REFACTOR cycle:

1. **RED** — Write the smallest test that captures the next piece of desired
   behavior. Run it and confirm it fails *for the right reason* (the behavior is
   missing — not a typo or import error).
2. **GREEN** — Write the minimum code needed to make that test pass. Resist
   adding anything the test doesn't require yet.
3. **REFACTOR** — With tests green, clean up names, duplication, and structure.
   Re-run the tests to confirm they stay green.

Rules:
- One behavior per cycle. Don't write five tests then all the code.
- For a bug fix, first write a test that **reproduces the bug** (RED), then fix
  it (GREEN). This proves the fix and guards against regression.
- Match the project's existing test framework and conventions (for Khali:
  `pytest` + `pytest-asyncio`). Read a neighboring test file first.
- Never weaken or delete a test just to make the suite pass.

Run the full relevant test suite before declaring the work done, and report the
actual result.
