# AGENTS.md

**Who this is for:** AI coding agents (Claude Code, GitHub Copilot, Codex) working in this repository. People
start with [README.md](README.md).

**How the instructions are layered:**

- **This file** is always loaded.
- **Path-scoped rules** in [.github/instructions/](.github/instructions/) load when you work on matching files.
  `.claude/rules` is the same directory.
- **Skills** in [.claude/skills/](.claude/skills/) load when a task needs them.
- **Depth** is in [docs/](docs/README.md).

## What this is

`j2gha` is a Jenkins → GitHub Actions analysis, conversion and differential-validation harness:

- it parses a Jenkinsfile with Jenkins' own Groovy;
- converts it deterministically to a workflow and a migration report;
- validates the workflow;
- runs the original on a disposable Jenkins and the conversion on act or GitHub runners, and compares the runs.

It is a **prototype (proof of concept)**, not a production migration tool. Report results as what the runs showed: an
*equivalent* verdict means no difference was found, never that a conversion is correct.

## What you need, and where to find it

| You need to... | Read | Skill |
|---|---|---|
| Set up, run the CLI | [docs/prerequisites.md](docs/prerequisites.md), [docs/usage.md](docs/usage.md) | `jenkins-to-gha` |
| Convert a user's own (private) pipeline | [docs/own-pipelines.md](docs/own-pipelines.md) | `jenkins-to-gha` |
| Explain a difficulty score or migration report | [docs/scoring.md](docs/scoring.md), [docs/own-pipelines.md](docs/own-pipelines.md) | `jenkins-to-gha` |
| Look up Jenkins or GitHub Actions facts | [docs/documentation.md](docs/documentation.md) | `jenkins-docs`, `gha-docs` |
| Add or change a conversion rule | [docs/extending.md](docs/extending.md), [docs/self-improvement.md](docs/self-improvement.md) | `j2gha-rule-improver` |
| Add corpus examples, or make one run to completion | [docs/results.md](docs/results.md), [docs/scoring.md](docs/scoring.md) | `jenkins-example-crawler`, `jenkins-example-twin` |
| Understand the design | [docs/mechanism.md](docs/mechanism.md), [docs/architecture.md](docs/architecture.md) | |
| Use GitHub Copilot or a local model | [docs/copilot.md](docs/copilot.md) | |
| Find any other page | [docs/README.md](docs/README.md) | |

## Layout

The pipeline is parse → IR → assess → generate → validate → execute and compare.

- **Each stage writes into the pipeline's directory.** It writes `analysis/`, `gha/` and `runs/`, and owns a
  marker-delimited README section (`<!-- j2gha:<section>:start/end -->`, `j2gha/readme.py`), so every stage can be
  re-run on its own.
- **Stages are orchestrated** in `j2gha/stages.py`, and the CLI is `j2gha/cli.py`.

| Path | What | Rules |
|---|---|---|
| `j2gha/analysis/`, `j2gha/ir.py`, `j2gha/rules/steps.yaml` | parse, IR, step catalog, findings, difficulty score | `parser` |
| `j2gha/convert/` | workflow generator, workspace hand-off | `generator` |
| `j2gha/validate/` | actionlint, zizmor, policy checks | `validation` |
| `j2gha/jenkins/`, `j2gha/runners/`, `j2gha/trace.py`, `j2gha/outputs.py`, `j2gha/provenance.py` | localiser, runs, comparison | `execution` |
| `j2gha/gha/`, `j2gha/github.py` | remote runs, budget guard, GitHub client | `remote` |
| `j2gha/docs/`, `j2gha/rules/docs-xref.yaml` | reference-docs bundles | `reference-docs` |
| `docker/` | harness images, Jenkins plugins | `images` |
| `examples/` | the corpus: originals `0NN`, twins `1NN`, walkthrough `000` | `corpus` |
| `evals/` | human-owned eval inputs | `evals` |
| `tests/` | unit and e2e tests | `tests` |
| `docs/`, `README.md`, `CHANGELOG.md`, agent material | documentation | `docs` |

## Commands

```bash
uv sync                                            # deps
uv run --group dev pytest -q                       # unit tests (no Docker needed)
uvx ruff check j2gha tests --select F,E9,B --ignore B008                  # lint
uv run --group dev pytest -q -m e2e tests/test_walkthrough.py   # example 000, Jenkins vs act (~4 min, Docker)

uv run j2gha docker build [--only jenkins|act|act-runner|runner]   # harness images
uv run j2gha add PATH [--name N] [--force]         # own pipeline (any file name) -> $J2GHA_PIPELINES_DIR/N/Jenkinsfile
uv run j2gha analyze|convert|validate [ids|all]    # ids: 003, 1-5, "004 009", names; all (default) = corpus, or
                                                   # every pipeline in J2GHA_PIPELINES_DIR (--pipelines-dir) when set
uv run j2gha pipeline <ids> [--continue-on-invalid]   # analyze -> convert -> validate -> run (jenkins,act)
uv run j2gha run <ids> --tier jenkins,act [--mode trace|full] [--branch B] [--param NAME=VALUE ...]
uv run j2gha run <ids> --tier selfhosted           # real GitHub Actions via local JIT runners, 0 minutes
uv run j2gha run <ids> --tier hosted --yes --max-minutes N   # spends minutes: user approval + `j2gha budget` first
J2GHA_OFFLINE=1 uv run j2gha pipeline <ids>        # or --offline: no GitHub API calls (cache only), no fetches
uv run j2gha summary                               # examples/README.md, or $J2GHA_PIPELINES_DIR/README.md when set
uv run j2gha crawl --count N [--dry-run]           # add N scored corpus examples (gh auth, Jenkins image)
uv run j2gha gaps [--unmapped-only] | scoreboard [--check] | guard [--base main]   # rule-improvement evals
uv run j2gha budget | environments [list|clean] | jenkins up|down|status
uv run j2gha docs fetch [jenkins|gha] [--version fpt|ghec|ghes-X.Y] | docs status|path|use|xref
```

`uv run j2gha --help` lists every option.

## Rules that apply everywhere

- **Users' own pipelines are private.**
  - Keep them in `J2GHA_PIPELINES_DIR`, outside the clone; never add them to `examples/` or to a commit.
  - Do not point the remote tiers at them. The harness refuses unless `J2GHA_REPO` is private.
  - `J2GHA_OFFLINE=1` stops the harness's own network use.
- **Hosted runs spend GitHub Actions minutes:** only with the user's explicit go-ahead, after `uv run j2gha budget`.
  Prefer `--tier selfhosted`.
- **No operator credentials in runs.** Runs use fake credentials. Remote jobs still get GitHub's automatic
  `GITHUB_TOKEN`, so don't call runs credential-free.
- **Never edit a cited `examples/0NN/Jenkinsfile`.** Never hand-edit generated files (`analysis/`, `gha/`, `runs/`,
  README sections): regenerate them.
- **`evals/` is human-owned.** Only a human runs `scoreboard --write`.
- **README.md stays short.** Detail goes in the relevant `docs/` page.
- **Maintain CHANGELOG.md.** Every user-visible change adds its entry under `## [Unreleased]` (Added / Changed /
  Fixed / Removed) in the same commit or pull request.
  - User-visible means a command, option, environment variable, behaviour, output or doc a user follows.
  - A new feature's entry says how to use it: a command or two.
  - Internal refactors and test-only changes need no entry.
  - A release moves `[Unreleased]` under `## [X.Y.Z] - date`, bumps `version` in `pyproject.toml`, tags `main`
    `vX.Y.Z` and updates the compare links. `v0.1.0` is the initial proof of concept.
- **Keep this material accurate.**
  - When you change behaviour that a rule file or skill describes, update it in the same change.
  - `tests/test_agent_docs.py` checks links, rule globs and skill frontmatter.
  - Older Claude Code versions (before 2.1.277) do not read `AGENTS.md`. For them, create an untracked `CLAUDE.md`
    containing `@AGENTS.md`; it is gitignored.
