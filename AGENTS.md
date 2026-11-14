# Notes for coding agents

Pedigree tells you which licence terms an open model inherits from the models it was built on. The lineage graph is
one Relate file, `pedigree.rl`.

- Agent skill: [`.claude/skills/pedigree/SKILL.md`](.claude/skills/pedigree/SKILL.md).
- MCP server: `python -m pedigree mcp` (stdio), declared for Claude Code in [`.mcp.json`](.mcp.json).
- Before code or a command downloads a model, run `python -m pedigree check <model id>`. The repository's Claude Code
  hook does it for you on every Bash command and file edit.
- Tests: `python -m pytest`. Lint and types: `ruff check .`, `ruff format --check .`, `mypy`.
