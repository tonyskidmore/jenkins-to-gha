# Changelog

All notable changes to `j2gha` are recorded here, newest first.

- **Format:** loosely [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- **Versions:** follow [Semantic Versioning](https://semver.org/). While the version is below 1.0, a minor release may
  change behaviour.
- **How to use it:** an entry for a new feature says how to use it.
- **Status:** the project is a proof of concept; see the README's *Where it stands*.

## [Unreleased]

Your own (private) pipelines, offline use, and GitHub Copilot.

### Added

- **A pipelines directory outside the clone.** Set `J2GHA_PIPELINES_DIR` (or pass `--pipelines-dir DIR`). Each
  pipeline gets a subdirectory there, and everything the stages write for it goes there too. Nothing is written into
  this repository's tracked `examples/`.
  - `all` (and a command given no ids) means every pipeline in that directory.
  - Corpus ids such as `003` still resolve to `examples/`.

  ```bash
  export J2GHA_PIPELINES_DIR=~/j2gha-pipelines
  uv run j2gha add /path/to/payments/Jenkinsfile
  uv run j2gha pipeline                     # analyse, convert, validate, Jenkins and act trace runs, for all of them
  ```

- **`j2gha add PATH [--name N] [--force]`.** Copies a Jenkinsfile into the pipelines directory as `N/Jenkinsfile`.
  - The file can have any name, e.g. `Jenkinsfile.deploy` or `ci/build.groovy`.
  - The default name is the file's directory, plus the file name when that is not `Jenkinsfile`.
  - A changed file needs `--force`.

  ```bash
  uv run j2gha add ~/src/payments/Jenkinsfile.deploy          # -> payments-jenkinsfile-deploy
  uv run j2gha add ~/src/shared/vars/buildApp.groovy --name build-app
  ```

- **An index of your pipelines.** With a pipelines directory set, `uv run j2gha summary` writes
  `$J2GHA_PIPELINES_DIR/README.md`, one row per pipeline: dialect, difficulty, hard gates, automation, validation and
  trace results.
- **Offline mode.** Set `J2GHA_OFFLINE=1` (or pass `--offline`), and the harness makes no GitHub API calls and fetches
  nothing.
  - `convert` pins only actions whose commit SHAs are already cached; the rest keep their tags, which it reports.
  - The remote tiers are refused, and so is a full-mode run that would fetch a source repository. The local tiers
    still run.
  - `docs fetch`, `crawl`, `budget` and `environments` stop with a message.

  ```bash
  J2GHA_OFFLINE=1 uv run j2gha pipeline payments
  ```

- **A breakdown of every difficulty score.** It appears in three places:
  - **`analyze`** (and `pipeline`) prints the dimensions and hard gates under the summary line. When the pipeline calls
    steps j2gha does not know, it also names them, with the score as if they were mapped.
  - **The README analysis table** gains an *If every unknown step were mapped* row.
  - **The migration report** opens with a *Difficulty breakdown* section.

  ```text
  [j2gha] 017: declarative      difficulty  36 (assisted), coverage 82.8%, convertibility partial
  [j2gha] 017:   structure 10, mapping 4.3, plugins 6, library 11, runtime 4, security 0, flow 1; hard gates: none
  [j2gha] 017:   1 unknown step(s) (fail): 34 (assisted) if they were mapped
  ```

- **One set of agent instructions for Claude Code, GitHub Copilot and Codex.**
  - **`AGENTS.md`** is the short root file, always loaded: what j2gha is, a "what you need → what to read" table, the
    layout, the commands, and the rules that apply everywhere.
  - **Eleven path-scoped rule files** in `.github/instructions/` carry the developer detail. They have both `applyTo`
    (Copilot) and `paths` (Claude Code) frontmatter, and `.claude/rules` is the same directory. An agent loads a rule
    only when it works on matching files.
  - **`tests/test_agent_docs.py`** keeps it accurate: links, rule globs, skill and agent frontmatter, the hook.

  ```bash
  copilot instruction list      # AGENTS.md and the eleven rule files, each with its globs
  ```

- **`j2gha-migrator`, a GitHub Copilot custom agent** (`.github/agents/`). It packages the migration workflow with its
  rules: keep pipelines local, explain before editing, edit only a copy of the workflow, and never change j2gha itself.

  ```bash
  copilot --agent j2gha-migrator   # then: "add ~/src/payments/Jenkinsfile and tell me what its migration needs"
  ```

- **A Copilot hook** (`.github/hooks/`) that asks before an agent starts a GitHub-hosted run. Set
  `J2GHA_AGENT_HOSTED=1` to let the agent start hosted runs itself.
- **[`docs/README.md`](docs/README.md)**: every docs page with its readers, and what to update when code changes.
- **New docs:**
  - [`docs/own-pipelines.md`](docs/own-pipelines.md): converting your own pipelines. Covers what each stage sends off
    the machine, reading the results, why shared-library pipelines rate *significant-redesign*, shared libraries,
    missing plugins, full mode, and using the converted workflow.
  - [`docs/copilot.md`](docs/copilot.md): using GitHub Copilot with the skills. Covers what Copilot CLI, VS Code and
    the cloud agent read, example prompts, settings for private pipelines, and local models.
  - [`docs/scoring.md`](docs/scoring.md), new section *Migration difficulty (0-100)*: every dimension, the hard gates,
    the bands, convertibility, and how unknown steps count.

  ```bash
  copilot --add-dir "$J2GHA_PIPELINES_DIR"  # in the clone; then ask: "use the jenkins-to-gha skill to analyse payments"
  ```

### Changed

- **Difficulty scoring (analysis version 2).** Shared-library pipelines no longer rate significant-redesign just
  because they load a library.
  - **`SharedLibrary` is no longer a hard gate**, so it no longer floors the score at 46. It stays a high-severity
    finding.
  - **An unknown step counts once** beyond coverage: in library opacity when a library is loaded, otherwise in plugin
    coupling. Before, it counted in both.
  - **Convertibility is `partial`** whenever unknown steps remain.
  - **Weighted coverage is unchanged.**
  - **Corpus effect:**
    - 003/103 55 → 43, 010 67 → 58, 017/117 46 → 36, 008/108 60 → 54;
    - 005, 006 and 106 go `automatic` → `partial`.

  The committed corpus results were regenerated. Details: [`docs/scoring.md`](docs/scoring.md#unknown-steps).
- **The selfhosted and hosted tiers refuse a pipeline that is not a corpus example**, unless `J2GHA_REPO` names a
  repository the GitHub API reports as private (or internal).
  - Before, such a pipeline was pushed to the clone's `origin`, which is this public repository.
  - The local tiers in the same command still run, and the refusal exits with status 3.
- **A named pipeline without a `Jenkinsfile` now gets a clear error** instead of a crash in `convert`.
- **Generated files name your own pipeline by its directory name**, never by an absolute local path.
- **The docs now cover GitHub Copilot as well as Claude Code.** `AI.md`, `skills.md` and `usage.md` say that Copilot
  reads the same skills and instructions.
- **`CLAUDE.md` is replaced by `AGENTS.md`.** Claude Code 2.1.277 and later read `AGENTS.md`. For an older Claude Code,
  create a local `CLAUDE.md` containing `@AGENTS.md`; it is gitignored.
- **The skills work under Copilot too.**
  - They refer to the user's request instead of `$ARGUMENTS`, which Copilot does not substitute.
  - They name tools generically.
  - The two video skills are `disable-model-invocation`: invoke them by name.
  - `jenkins-to-gha` gains *Reviewing a migration report* and knows the pipelines directory.
  - The crawler skill now includes the licence step.
  - The rule improver says how to work under the Copilot cloud agent.

## [0.1.0] - 2026-10-13

The initial proof of concept: `main` at the end of the first public release (pull requests #1-#6).

- **Analysis.** Parses a Jenkinsfile with Jenkins' own Groovy 2.4 AST into a typed model. Declarative pipelines are
  interpreted directive by directive; scripted ones get a best-effort model. It then scores the migration difficulty
  (0-100) from seven dimensions and hard gates.
- **Conversion.** A deterministic generator writes a GitHub Actions workflow and a migration report listing each
  construct as mapped, approximated, manual or dropped, by source line. It covers:
  - jobs planned from agents, parallel, matrix and `input` stages;
  - workspace hand-off between jobs;
  - `when` conditions;
  - credentials as secrets;
  - action pinning.
- **Validation.** actionlint (with shellcheck), zizmor and the project's own policy checks.
- **Differential execution.** The original runs on a disposable local Jenkins (JCasC); the conversion runs on act,
  ephemeral self-hosted runners or GitHub-hosted runners, behind a minutes budget guard.
  - Trace mode compares control flow stage by stage.
  - Full mode compares real runs, JUnit cases and archived files.
  - Run records carry provenance, so stale ones are not counted.
- **Corpus.** 20 cited real-world Jenkinsfiles and 16 *twins* (minimally edited copies that run to completion).
  - In trace mode, 15 of the 20 conversions matched Jenkins.
  - In full mode, 12 of the 16 twins showed no difference on real GitHub Actions.
- **Agent support (optional).** Claude Code skills, plus version-pinned Jenkins and GitHub Actions reference docs for
  agents (`j2gha docs`):
  - a crawler;
  - the harness driver;
  - twins;
  - a rule improver;
  - docs lookups;
  - videos.
- **Walkthrough.** Example 000 as a hands-on walkthrough, and narrated walkthrough videos.

[Unreleased]: https://github.com/tonyskidmore/jenkins-to-gha/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tonyskidmore/jenkins-to-gha/releases/tag/v0.1.0
