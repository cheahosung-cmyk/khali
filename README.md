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

After installing, plugin components are namespaced by plugin name, e.g.
`/khali-agent-tools:new-agent`.

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
setup.py                                # Python package (the Khali system)
```
