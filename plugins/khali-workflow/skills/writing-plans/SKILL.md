---
description: Use after the approach is agreed and before writing code for any multi-step change. Produce a precise, reviewable implementation plan and get approval first.
---

# Write a plan before coding

Turn an agreed direction into a concrete, gap-free plan that a reviewer can
sanity-check before any code is written.

The plan must include:

1. **Task breakdown** — ordered steps, each small enough to finish and verify in
   a few minutes. One logical change per step.
2. **Exact file paths** for every file you will create or modify. No vague
   "update the relevant module."
3. **Dependencies & order** — what must happen before what, and any new
   packages, migrations, or config required.
4. **Edge cases & failure modes** — what could go wrong and how each step
   handles it.
5. **Verification** — for each step, how you'll confirm it works (which test,
   command, or observable behavior).
6. **Out of scope** — what you are deliberately not doing, to prevent scope
   creep.

Present the plan and **get the user's approval before implementing.** When
approved, execute it step by step, checking off each item and re-verifying as
you go. If reality diverges from the plan, stop and revise the plan rather than
improvising silently.
