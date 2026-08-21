---
description: Review Khali agent code for correctness, concurrency safety, and resource cleanup
---

Review the selected code or recent changes as agent code in the Khali AI Agent
Management System. Focus on issues that matter for long-running agents:

- **Lifecycle correctness**: every `setup` has a matching `teardown`; resources
  (DB sessions, HTTP clients, tasks) are released even on the error path.
- **Concurrency safety**: no shared mutable state across `async` tasks without
  synchronization; no blocking calls inside the event loop; `await`ed
  coroutines aren't accidentally fired-and-forgotten.
- **Failure handling**: exceptions are caught at the right boundary, retried
  with backoff where appropriate, and never swallowed silently.
- **Config & secrets**: settings come from Pydantic models / env, not
  hardcoded; no secrets in logs.
- **Observability**: meaningful structured logs and clear error messages.

Be concise and actionable. Cite `file:line` for each finding and suggest the
concrete fix. Skip style nits unless they hide a real bug.
