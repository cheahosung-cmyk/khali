---
description: Use when starting a sizeable or risky change that benefits from an isolated workspace, or when juggling more than one branch at once. Set up and work in a git worktree.
---

# Use git worktrees for isolation

For a non-trivial feature or an experiment you might throw away, work in a
dedicated git worktree instead of mutating the main checkout. This keeps the
main branch clean and lets you switch contexts without stashing.

1. **Create a branch + worktree** off the base branch:
   ```shell
   git worktree add ../khali-<feature> -b feature/<feature>
   ```
2. **Work entirely inside that directory.** Build, run tests, and commit there.
   The main checkout stays untouched and usable.
3. **When done**, push the branch and open a PR from it.
4. **Clean up** once merged or abandoned:
   ```shell
   git worktree remove ../khali-<feature>
   git branch -d feature/<feature>
   ```

Guidance:
- One worktree per in-flight change; don't pile unrelated work into one.
- Never `git worktree add` onto an existing branch that's checked out elsewhere.
- Prune stale entries with `git worktree prune` if a directory was deleted
  manually.
