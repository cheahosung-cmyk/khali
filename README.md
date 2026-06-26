# khali

AI Agent Management System.

## Claude Code plugin marketplace

This repository doubles as a [Claude Code plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces). The catalog
lives in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).

### Add the marketplace

```shell
/plugin marketplace add cheahosung-cmyk/khali
```

> Note: the example in the task, `superpowers@claude-plugins-official`, refers to
> Anthropic's official marketplace, whose name is reserved. This repo publishes
> under `khali-tools` instead.

### Install a plugin

```shell
/plugin install khali-agent-tools@khali-tools
```

### Available plugins

| Plugin | What it adds |
| ------ | ------------ |
| `khali-agent-tools` | A `/new-agent` command to scaffold an agent, an `agent-review` skill, and an `agent-architect` subagent for designing agents. |
| `khali-workflow` | Structured senior-developer workflow skills that make Claude plan and verify before writing code, plus a `/ship` command that runs the whole flow. |
| `khali-trading` | Safety skills for building exchange/trading bots — resilient API boundaries, live-money review, and disciplined backtest iteration. |

After installing, plugin components are namespaced by plugin name, e.g.
`/khali-agent-tools:new-agent` or `/khali-workflow:ship`.

#### `khali-workflow` skills

These activate automatically based on context (no slash command required), in
the spirit of [obra/superpowers](https://github.com/obra/superpowers):

| Skill | When it kicks in |
| ----- | ---------------- |
| `brainstorm` | Before building a feature — study the code and weigh approaches first. |
| `writing-plans` | After the approach is agreed — write a precise, approved plan before coding. |
| `test-driven-development` | When implementing or bug-fixing — RED → GREEN → REFACTOR. |
| `systematic-debugging` | When something breaks — hypothesis + isolation, three-strike rule. |
| `requesting-code-review` | Before declaring work done — self-review the full diff. |
| `using-git-worktrees` | For sizeable or risky changes — work in an isolated worktree. |

#### `khali-trading` skills

For building automated trading bots. They auto-activate when you work on
exchange/order code:

| Skill | When it kicks in |
| ----- | ---------------- |
| `api-boundary-guard` | Writing/editing any exchange API call — wraps it in try/catch, 3× exponential-backoff retry on transient errors, loud alert on failure, idempotent order ids. |
| `trade-safety-review` | Before going live or reviewing order/risk code — checks live-vs-test isolation, order correctness, risk limits, `Decimal` money, secret handling. |
| `backtest-loop` | Iterating a backtest until green — disciplined run-fix-rerun with three-strike rule, plus overfitting/look-ahead/fees-and-slippage guards. |

> **Not financial advice.** These skills enforce engineering safety practices.
> Test on a testnet/paper account before risking real funds; live trading is
> your decision and responsibility.

> Want the original? Install Superpowers itself in your local Claude Code:
> `/plugin install superpowers@claude-plugins-official` (or
> `/plugin marketplace add obra/superpowers-marketplace` then
> `/plugin install superpowers@superpowers-marketplace`). `khali-workflow` is a
> lightweight, Khali-flavored take on the same idea — not a fork.

### Develop and test locally

```shell
# Validate the marketplace and plugin manifests
claude plugin validate .

# Add this checkout as a local marketplace and install from it
/plugin marketplace add ./
/plugin install khali-agent-tools@khali-tools
```

## Repository layout

```
.claude-plugin/marketplace.json        # marketplace catalog
plugins/
  khali-agent-tools/
    .claude-plugin/plugin.json          # plugin manifest
    commands/new-agent.md               # /new-agent command
    skills/agent-review/SKILL.md        # agent-review skill
    agents/agent-architect.md           # agent-architect subagent
  khali-workflow/
    .claude-plugin/plugin.json          # plugin manifest
    commands/ship.md                    # /ship — run the full workflow
    skills/brainstorm/SKILL.md
    skills/writing-plans/SKILL.md
    skills/test-driven-development/SKILL.md
    skills/systematic-debugging/SKILL.md
    skills/requesting-code-review/SKILL.md
    skills/using-git-worktrees/SKILL.md
  khali-trading/
    .claude-plugin/plugin.json          # plugin manifest
    skills/api-boundary-guard/SKILL.md
    skills/trade-safety-review/SKILL.md
    skills/backtest-loop/SKILL.md
setup.py                                # Python package (the Khali system)
```
