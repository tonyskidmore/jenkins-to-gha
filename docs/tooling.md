# Tooling: what we use, and what we looked at but did not adopt

Last reviewed October 2026. This page records the analysis, linting and execution tools behind the
Jenkins → GitHub Actions pipeline and the reasons for the tools we left out, so the question is not re-opened without
new information.

## What we use

| Tool | Version | Role | Where |
|---|---|---|---|
| **actionlint** | 1.7.12 (image pinned) | Structural lint of the generated workflow: syntax, expressions, contexts, runner labels. Its shellcheck integration is our SAST for the converted `sh` bodies. Structural findings block validation; shellcheck findings are reported but do not. | `validate/static.py` |
| **zizmor** | 1.30.1 (image pinned) | Security audit of the workflow (template injection, dangerous triggers, excessive permissions, unpinned actions and images, artipacked). Runs `--offline`. Findings are advisory, but a run that fails to execute is a failure. | `validate/static.py` |
| **j2gha policy checks** | in-tree | Rules specific to converted output. Errors, which block validation: no top-level `permissions`, `pull_request_target`, event-data script injection, invalid YAML and the context checks. Warnings, reported only: a job without `timeout-minutes`, an action not pinned to a SHA, unresolved Groovy. Informational: manual-migration placeholders. | `validate/static.py`, `validate/contexts.py` |
| **act** | 0.2.89 (sha256-pinned) | Fast local execution tier. A smoke test, not a fidelity oracle: only `@v4` artifact actions work. See `docs/act-evaluation.md`. | `docker/act/Dockerfile`, `runners/` |
| **Ephemeral self-hosted runners** | `j2gha/runner:local` (digest-pinned `actions-runner` base + the Jenkins toolchain) | Real GitHub Actions execution through local just-in-time runners, with no minutes spent. The preferred remote tier. The act job container (`j2gha/act-runner:local`) is built the same way. | `docker/runner/`, `docker/act-runner/`, `runners/`, `gha/` |
| **GitHub-hosted runners** | n/a | Last-resort execution, behind the minutes budget guard and explicit user approval. | `gha/budget.py` |
| **Jenkins controller** | digest-pinned base, plugins pinned in `plugins.txt` | Reference execution of the original Jenkinsfile, and the Groovy 2.4 AST used for parsing. | `docker/jenkins/`, `jenkins/` |
| **Jenkins Configuration as Code (JCasC)** | `configuration-as-code` plugin, pinned in `plugins.txt` | Configures the disposable controller declaratively (local admin user, 16 executors, common agent labels, standard crumb issuer, no setup wizard), so every build of the image starts identically. The controller is local-only; script approval is handled separately through the script console (see `.github/instructions/execution.instructions.md`). | `docker/jenkins/casc/jenkins.yaml` |
| **pytest, ruff** | dev group / `uvx` | Unit tests (the only check CI runs) and lint (`ruff --select F,E9,B`, run locally). | `tests/`, `pyproject.toml` |

Every scanner in the table runs without network access or credentials. Execution variants replace secrets with the
`FAKE_*` values (see `.github/instructions/execution.instructions.md`).

## Evaluated and not adopted

Five tools were built from their release tags and scored out of 10 against the actionlint + zizmor + policy stack, on
the 20 generated workflows, 56 run logs and a set of seeded defects. The adopt threshold was 7; nothing reached it.
The rubric and per-tool reviews were kept on local `eval/*` branches that are not published; the table below is their
summary.

| Tool | Score | Decision | Why |
|---|---:|---|---|
| **gitleaks** v8.30.1 | 5.6 | Not now; **possible future addition** | The only tool that catches secrets leaked in run logs (unmasked tokens, cloud keys) and literals in workflows, with no false positives on our data. But the converter does not currently emit literals and our logs are clean, so it guards against a threat we do not see today. Its default rules also miss the harness's own `J2GHA_ENV_CANARY`. |
| **ghalint** v1.5.6 | 5.3 | Not now; **possible future addition** | Found one real issue nothing else flagged: workflow-level `env` exposing a secret to every job (example 009). Most other policies duplicate zizmor or our policy checks, and its `job_permissions` policy is noisy on our output. Log-line output only, no per-file mode. |
| **poutine** v1.1.6 | 4.8 | Rejected | Agrees with zizmor on every injection and untrusted-checkout case. Adds only `curl \| sh` detection. The largest dependency-risk surface of the five (12 reachable advisories, mostly SSH and a pre-release go-git, likely not on the `analyze_local` path but not verified). |
| **pinact** v5.0.0 | 3.0 | Rejected as a validator | Offline it only checks for a 40-character SHA, which the corpus already satisfies and three existing checks already cover. Its distinctive comment-vs-SHA check needs the GitHub API. It could still be useful as a generation-time pin fixer, which is a separate question. |
| **check-jsonschema** 0.38.2 | 3.0 | Rejected | Duplicates actionlint's structural checks and found nothing on the corpus. |

### Gitleaks and ghalint: not a good value against effort today

Both could be included in future. For now we decided the value does not justify the effort of adding and maintaining
them: each needs a pinned build, a new run mode and output parsing, and a triage step, and each would currently
produce almost nothing the existing stack does not already report.

Things that would change that:

- **gitleaks:** the converter starts emitting literal values, or hosted-run logs are retained and need scanning for
  unmasked secrets. It would run as an advisory step over the logs and artifacts `j2gha run` already writes.
- **ghalint:** a cheaper route exists. Its one valuable rule (`workflow_secrets`) is a few lines in `policy_checks`,
  and the real fix is in the generator (scope the env var to the jobs that use it). Adopt the tool itself only if
  several more of its policies prove useful.

### Screened but not scored

These were ruled out on repository health, licence, or fit, using the GitHub API and web research on 2026-10-09
rather than a hands-on run. Treat the reasons as indicative.

| Tool | Reason |
|---|---|
| octoscan | GPL-3.0, no commits in 90 days, heavy overlap with zizmor. |
| action-validator | GPL-3.0, no commits in 90 days. Its one unique check (`paths` globs match real files) is minor. |
| trufflehog | AGPL-3.0. gitleaks covers the same need with a permissive licence. |
| frizbee | Pre-1.0, redundant with zizmor's pinning audit. |
| gato-x | Needs a GitHub token and has no local-file mode. |
| OpenSSF Scorecard | Repository-oriented and needs API context; its workflow checks overlap zizmor. |
| CodeQL for Actions | Heavy (database build per run) for per-file validation; overlaps zizmor. |
| Harden-Runner | Runtime egress monitor that depends on a SaaS service, with 5 published advisories (egress-policy bypasses, since patched). |
| Falco Actions, Tracee Action | Falco Actions has no releases; Tracee Action's repository is archived. Both need eBPF access, so they would not work under act. |
| wrkflw | Pre-1.0; duplicates actionlint and act. |
| act-js / mock-github | Dormant (last release 2024-04). Step-level mocking is an idea to borrow, not a dependency. |
| sisakulint | Young (pre-1.0, 93 open issues). A candidate to trial later. |
| yamllint | Style only. |

### Ideas not built

- **GitHub Actions Importer `dry-run`** as an independent second conversion to diff against.
- **An injection probe under act**, running the converted workflow with a hostile `github.event.*` payload.
- **Mutation tests** extending `--edited-model` (mutate `when` conditions, hand-off, trace parity and check the
  comparator flags each one).

## Open items found during the evaluation

Neither is fixed yet.

- The policy check `no-pull-request-target` only inspects `on` when it is a mapping, so `on: pull_request_target` as a
  string, or `on: [pull_request_target]`, is not flagged. zizmor does catch it.
- The generator maps a Jenkins credential into workflow-level `env` (example 009, `GITHUB_TOKEN`), exposing it to every
  job. No current check flags this.
