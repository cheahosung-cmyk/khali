---
description: Use BEFORE building a new feature or making a non-trivial change. Refine the idea, study the codebase, and weigh architecture and trade-offs before writing any code.
---

# Brainstorm before building

Do NOT jump to implementation. First understand the problem and the existing
system, then propose a direction.

1. **Restate the goal** in one or two sentences. If the request is ambiguous,
   ask the user the one or two questions that actually change the design —
   don't guess on decisions that are theirs to make.
2. **Study what exists.** Read the relevant modules, recent commit history, and
   tests. Note the conventions, abstractions, and constraints already in place.
   Reuse them; don't invent a parallel pattern.
3. **Lay out 2-3 viable approaches.** For each, state the trade-offs:
   complexity, blast radius, performance, testability, and how well it fits the
   existing architecture.
4. **Recommend one** and say why. Call out the risks and the parts you're
   unsure about.
5. **Stop and confirm** the direction with the user before moving to a detailed
   plan or code.

Keep it concise and specific to this repository. The output of this step is a
shared understanding, not code.
