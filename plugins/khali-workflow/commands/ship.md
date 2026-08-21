---
description: "Drive a change through the full structured workflow: brainstorm, plan, TDD, review"
argument-hint: <what to build or fix>
---

Take the following task through the full khali-workflow, stopping for approval
at each gate instead of jumping straight to code:

> $ARGUMENTS

1. **Brainstorm** — restate the goal, study the codebase and history, lay out
   2-3 approaches with trade-offs, recommend one, and confirm the direction.
2. **Plan** — write a precise, step-by-step implementation plan with exact file
   paths, dependencies, edge cases, and per-step verification. Get approval.
3. **Implement with TDD** — for each step, write a failing test first, make it
   pass with minimal code, then refactor. Match the project's test conventions.
4. **Self-review** — re-read the full diff for correctness, regressions,
   tests, and cleanup. Run the suite and report the real result.

If `$ARGUMENTS` is empty, ask what to build before starting. Don't skip the
brainstorm and plan gates for anything beyond a trivial one-liner.
