# Documentation

Every page in `docs/`, the readers it is for, and what to update when something changes.

- **Readers:** *users* run `j2gha` on pipelines; *developers* change j2gha itself; *agents* are AI coding assistants.
  Agents start from [AGENTS.md](../AGENTS.md) and the rule files in `.github/instructions/`.
- **Getting started:** [README.md](../README.md), then the hands-on [walkthrough](../examples/000/README.md).

## Using j2gha

| Page | What it covers | For |
|---|---|---|
| [prerequisites.md](prerequisites.md) | What to install, disk and memory, versions in use | users |
| [usage.md](usage.md) | The CLI: corpus runs, real GitHub Actions runs, minutes, reference docs | users |
| [own-pipelines.md](own-pipelines.md) | Converting your own (private) pipelines: the pipelines directory, `j2gha add`, what leaves the machine, offline mode, reading results, shared libraries, plugins | users |
| [scoring.md](scoring.md) | The migration difficulty score (0-100) and the crawler's example score (0-10) | users, developers |
| [results.md](results.md) | What the runs showed on the corpus, and the reference runs | users |
| [copilot.md](copilot.md) | Using GitHub Copilot: what it reads, skills, the migrator agent, private pipelines, local models | users, agents |
| [skills.md](skills.md) | The agent skills and how they chain | users, agents |
| [AI.md](AI.md) | What needs an AI agent (nothing does), and how AI built this repository | users |
| [walkthrough-videos.md](walkthrough-videos.md) | The narrated walkthrough videos | users |

## How it works

| Page | What it covers | For |
|---|---|---|
| [mechanism.md](mechanism.md) | The core idea: two ASTs, an IR, classification, deterministic generation, differential runs | users, developers |
| [architecture.md](architecture.md) | Stages, components, design decisions, security posture, known limitations | developers |
| [extending.md](extending.md) | Adding or changing a conversion rule, step by step | developers |
| [self-improvement.md](self-improvement.md) | Letting an agent propose rule changes: design, evals, risks | developers |
| [documentation.md](documentation.md) | The version-pinned Jenkins and GitHub Actions docs bundles for agents | developers, agents |

## Background

| Page | What it covers | For |
|---|---|---|
| [research.md](research.md) | The initial research notes | developers |
| [tooling.md](tooling.md) | Scanners and tools adopted, and those evaluated and rejected | developers |
| [act-evaluation.md](act-evaluation.md) | Whether nektos/act is still worth using, and in what role | developers |
| [docs-evaluation.md](docs-evaluation.md) | How agents should look up documentation: an evaluation of methods | developers |
| `video/` | Sources for the walkthrough videos | developers |

## Keeping the docs current

| When you change... | Also update |
|---|---|
| A command, option or environment variable | `uv run j2gha --help` text, [usage.md](usage.md) or [own-pipelines.md](own-pipelines.md), the *Commands* block in `AGENTS.md`, `CHANGELOG.md` |
| How a pipeline is scored | [scoring.md](scoring.md), `.github/instructions/parser.instructions.md`, and the corpus results (regenerated offline) |
| Conversion behaviour | `.github/instructions/generator.instructions.md`, [architecture.md](architecture.md), [extending.md](extending.md) if it changes how a rule is added |
| Localisation, runs or the comparison | `.github/instructions/execution.instructions.md`, [mechanism.md](mechanism.md), [architecture.md](architecture.md) |
| Remote runs, the budget guard or what reaches GitHub | `.github/instructions/remote.instructions.md`, [own-pipelines.md](own-pipelines.md) (*What leaves your machine*), [usage.md](usage.md) |
| A skill | its `SKILL.md`, [skills.md](skills.md); [copilot.md](copilot.md) if Copilot users see it |
| Results on the corpus | [results.md](results.md), the README's figures |
| Anything a user would notice | `CHANGELOG.md`, under `[Unreleased]` |

`tests/test_agent_docs.py` checks that relative links resolve in these pages, `AGENTS.md`, the rule files and the
skills.
