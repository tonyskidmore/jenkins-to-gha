# AI and this repository

## Do I need an AI agent?

**No.** The `j2gha` command line runs without Claude Code or any other AI agent, and needs no LLM API key. Nothing in
`j2gha/` calls a model: the parser, assessment, the generator (which owns the YAML; no free-form LLM output), validation,
execution, `docs fetch` and `budget` are plain Python plus Docker, `gh` and the network.

Everything agent-related is optional:

| Element | Needs an agent? | What it is |
|---|---|---|
| `j2gha ...` (every command in [usage.md](usage.md)) | No | Deterministic CLI |
| `.claude/skills/` | Optional (Claude Code, GitHub Copilot) | Skills that drive the CLI and read its results, look up reference docs, propose rule changes and make the videos. Each one is described in [skills.md](skills.md). |
| `AGENTS.md`, `.github/instructions/` | Optional (Claude Code, GitHub Copilot, Codex) | Project notes an agent loads automatically: `AGENTS.md` always, and a path-scoped rule file when it works on matching files (`.claude/rules` is the same directory). A human can read them as a developer guide. |
| `.github/agents/`, `.github/hooks/` | Optional (GitHub Copilot) | A custom agent for migration work, and a hook that asks before an agent starts a GitHub-hosted run ([copilot.md](copilot.md)). |

Claude Code and GitHub Copilot read the same files: the skills, `AGENTS.md` and the rule files. What else Copilot needs, and how
to use it with private pipelines or a local model, is in [copilot.md](copilot.md).

How the converter learns new Jenkins steps (a person or an agent adds catalog entries and generator code, then checks
them with tests and the differential run) is in [extending.md](extending.md). A starting point for letting an agent do
this, with its evals and risks, is [self-improvement.md](self-improvement.md).

## How AI was used to build this repository

- **Claude Code wrote most of it.** The starting point was the idea of a disposable Jenkins controller configured with
  Jenkins Configuration as Code (JCasC), plus `act` to run GitHub Actions workflows locally, as the basis of the
  automation. That idea came from a research conversation and became a written brief; the mechanism it settled on is in
  [mechanism.md](mechanism.md), and the research behind it in [research.md](research.md).
- **Codex CLI with Astra 6 reviewed Claude Code's work.** Each confirmed finding was fixed with a regression test
  (for example `tests/test_codex_review.py` and `tests/test_review_post_24bf0b6.py`).
- **Antigravity with Gemini 3.8 Flash explored the video ideas.** The starting point was
  [Claude Now Does Video (FOR FREE) Thanks To JavaScript](https://www.youtube.com/watch?v=rscb1DgJtNg) (Chase AI). The
  ideas that worked became the two video skills, `narrated-explainer` and `hyperframes-walkthrough` (see
  [skills.md](skills.md)), which made the [walkthrough videos](walkthrough-videos.md).

What an agent writes is checked the same way as anything else: unit tests, the differential runs and, for conversion
rules, the human-owned evals (see [extending.md](extending.md)).
