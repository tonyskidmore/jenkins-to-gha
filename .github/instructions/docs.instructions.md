---
description: "Writing the README, docs/ pages, the CHANGELOG and this agent material"
applyTo: "docs/**,README.md,CHANGELOG.md,AGENTS.md,.github/instructions/**,.github/agents/**,.claude/skills/**"
paths:
  - "docs/**"
  - "README.md"
  - "CHANGELOG.md"
  - "AGENTS.md"
  - ".github/instructions/**"
  - ".github/agents/**"
  - ".claude/skills/**"
---
# Docs and agent material

- **README.md stays short** (what it is, getting started, links): detail goes in the relevant `docs/` page.
- **`docs/README.md`** indexes every page with its audience. Add new pages there, and follow its *Keeping the docs
  current* table when code changes.
- **CHANGELOG.md:** every user-visible change gets an entry under `## [Unreleased]` (see `AGENTS.md`).
- **Agent material is shared by Claude Code and GitHub Copilot:**
  - `AGENTS.md` is the only root instruction file; keep it short and route to docs and rules.
  - Path-scoped rules live in `.github/instructions/*.instructions.md`, with both `applyTo` (Copilot) and `paths`
    (Claude Code) frontmatter; `.claude/rules` is a symlink to that directory.
  - Skills live in `.claude/skills/`: frontmatter `name`, `description`, optional `argument-hint` and
    `disable-model-invocation`; refer to the user's request rather than `$ARGUMENTS`, and name tools generically
    ("search", "a web-fetch tool").
  - `tests/test_agent_docs.py` checks links, globs and frontmatter.
- **Facts:** describe what the harness does now; report results as what the runs showed.

Reference: [docs/README.md](../../docs/README.md), [docs/copilot.md](../../docs/copilot.md).
