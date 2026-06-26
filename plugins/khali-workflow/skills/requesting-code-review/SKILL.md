---
description: Use after finishing an implementation and before declaring it done or opening a PR. Self-review the diff for correctness, regressions, and cleanup.
---

# Request code review

Before calling work complete, review your own diff with a critical eye — the
same way you'd review a teammate's PR.

1. **Re-read the full diff**, not just the files you remember touching. Run the
   equivalent of `git diff` and read every hunk.
2. **Correctness** — does it actually do what the plan/issue asked? Check edge
   cases, error paths, null/empty inputs, and concurrency where relevant.
3. **Regressions** — could this break existing callers or behavior? Look for
   changed signatures, shared state, and removed branches.
4. **Tests** — is the new behavior covered? Do the tests actually assert the
   intended outcome (not just "runs without error")? Run the suite and report
   the real result.
5. **Cleanup** — leftover debug prints, dead code, TODOs, commented-out blocks,
   inconsistent naming, or anything that doesn't match surrounding style.
6. **Scope** — is anything in the diff unrelated to the task? Pull it out.

List findings as `file:line` with a concrete fix for each. Fix what's clearly
yours to fix; flag anything ambiguous for the user. Only declare done once the
diff is clean and tests pass.
