---
description: Scaffold a new Khali agent module with boilerplate and tests
argument-hint: <agent-name>
---

Create a new agent module for the Khali AI Agent Management System named `$1`.

Follow the existing project conventions (FastAPI, Pydantic v2, SQLAlchemy 2.0,
async where appropriate). Produce:

1. An agent class under `src/agents/$1/` with:
   - A Pydantic config/settings model for the agent.
   - An async `run()` entry point and lifecycle hooks (`setup`, `teardown`).
   - Structured logging and error handling.
2. Registration of the agent in whatever registry the project already uses
   (inspect the codebase first; do not invent a new pattern if one exists).
3. A matching test module under `tests/agents/test_$1.py` using
   `pytest` and `pytest-asyncio`.

Before writing code, read the surrounding modules so the new agent matches the
project's naming, imports, and idioms. If `$1` is empty, ask which agent to
scaffold instead of guessing.
