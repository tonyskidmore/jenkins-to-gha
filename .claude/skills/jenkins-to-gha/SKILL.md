---
name: jenkins-to-gha
description: Drive the j2gha Jenkins-to-GitHub-Actions harness on examples/NNN - AST analysis, conversion to a GitHub Actions workflow with a migration report, static validation (actionlint/zizmor/policy), and differential execution of the original Jenkinsfile (disposable Jenkins in Docker) against the converted workflow (act, ephemeral self-hosted runners, or GitHub-hosted runners behind a minutes budget guard). Use when asked to analyse, convert, validate, test-run or compare Jenkins pipelines, or to check GitHub Actions minutes usage.
argument-hint: "<example ids | all> [--tier jenkins,act,selfhosted,hosted] [--mode trace|full]"
---

# Jenkins → GitHub Actions harness

All stages are `uv run j2gha <command>` sub-commands operating on `examples/NNN` directories. Each stage writes its
artifacts into the example directory and updates its own marker-delimited section of the example `README.md`.

| Stage | Command | Output |
|---|---|---|
| 1. Analysis | `j2gha analyze <ids>` | `analysis/{groovy-ast,jenkins-model,ir,analysis}.json`, README "Analysis (AST)" |
| 2. Conversion | `j2gha convert <ids>` | `gha/workflow.yml`, `gha/migration-report.md`, `gha/workflow.model.json` |
| 3. Static validation | `j2gha validate <ids>` | `gha/validation.json` (actionlint+shellcheck, zizmor, policy) |
| 4. Local execution | `j2gha run <ids> --tier jenkins,act` | `runs/jenkins-<mode>/`, `runs/act-<mode>/`, trace comparison |
| 5. Real GitHub Actions | `j2gha run <ids> --tier selfhosted` (no hosted minutes) or `--tier hosted --yes` (costs minutes) | `runs/<tier>-<mode>/` |
| 6. Minutes monitoring | `j2gha budget` | usage vs. included minutes; hosted runs are refused when over budget |

`j2gha pipeline <ids>` runs stages 1-4 in one go.

## Procedure

1. Resolve ids from `$ARGUMENTS` (`all`, `003`, `1-5`, `004 009`). Default tier `jenkins,act`, mode `trace`.
2. Make sure Docker is running. The Jenkins controller starts automatically (`j2gha jenkins up`), takes ~40 s the
   first time, and stays up for subsequent runs (`j2gha jenkins down` to stop it).
3. Run the stages in order (analysis must exist before conversion; conversion before validation/execution).
4. Summarise results per example from the README sections or the JSON artifacts: dialect, difficulty score and
   classification, automation %, validation status, and for each execution tier the result plus
   "equivalent / differs / inconclusive (similarity %)" versus the Jenkins reference. Inconclusive means Jenkins
   failed on the pipeline's own `error()` in a branch decided by stubbed runtime values (`comparison.inconclusive`
   names the stage); suggest a `--mode full` run rather than a generator fix.
5. For differences, open `runs/<tier>-trace/result.json` → `comparison.stages` and explain which stage/step
   diverged; fixes usually belong in `j2gha/convert/generator.py` (GHA side) or `j2gha/jenkins/localize.py`
   (Jenkins side).

## Looking things up

When explaining a difference or changing the generator, check facts against documentation instead of memory. Use
the `jenkins-docs` and `gha-docs` skills: they read the local, version-pinned bundles when they exist and fall back to
the web otherwise. `uv run j2gha docs xref <step...>` shows the catalog decision plus the Jenkins and GHA pages for a
construct.

## Modes

- `trace` (default): side-effecting steps are replaced by `J2GHA-TRACE {"stage","step"}` markers on both sides,
  so the comparison checks control flow (stage graph, when/post, parallel/matrix fan-out, script{} translation)
  independent of toolchains and credentials. Cheap: seconds per example, ~1 billable minute per job when hosted.
- `full`: real commands run. The Jenkins side checks out the original repository at the cited commit; the GHA side
  checks out the same commit. Expect environment-driven failures; compare overall outcomes, not traces.

## Safety rules

- Never run the `hosted` tier without the user's explicit go-ahead; it spends GitHub Actions minutes on a private
  repository. Run `uv run j2gha budget` first and pass `--max-minutes` to cap the worst case. The guard refuses runs
  that would exceed the remaining allowance minus a 20 % reserve, or the per-run cap, and requires `--yes` when
  not interactive.
- Prefer `--tier selfhosted` for real-GitHub validation: ephemeral JIT runners in local Docker cost no hosted
  minutes. Runner branches (`j2gha/run/...`) are orphan branches deleted after each run.
- Full-mode runs execute third-party build scripts. They run inside disposable containers; do not add the Docker
  socket (`run --docker`) unless the user accepts that the pipeline can control the host Docker daemon.
- The disposable Jenkins controller is bound to 127.0.0.1 with a local-only admin password and fake credentials;
  never point the harness at a real Jenkins.

## Useful environment variables

`J2GHA_INCLUDED_MINUTES` (default 2000; Pro 3000), `J2GHA_RESERVE_PCT` (20), `J2GHA_MAX_RUN_MINUTES` (30),
`J2GHA_REPO` (override the repository used for remote runs), `J2GHA_JENKINS_PORT` (18080),
`J2GHA_ALLOW_INCOMPLETE_USAGE=1` (let the guard accept a lower-bound jobs-API tally - the user's decision only).

The budget guard reads the billing usage of the **target repository's owner** (user or organization). If billing data
is unavailable it falls back to a jobs-API tally, which is a lower bound, and refuses hosted runs; for a user-owned
repository ask the user to run `! gh auth refresh -h github.com -s user`. `j2gha budget` lists pending minute
reservations (runs dispatched but not yet reconciled) and in-flight runs; `j2gha budget --clear ID...` clears a
reservation after its run has been checked by hand.

## Reading results and exit status

- Verdicts: *equivalent*, *differs*, *inconclusive* (the traces cannot decide - see the reason in the README), and
  ⏸️ *stale* for a run recorded against an earlier Jenkinsfile or conversion (re-run it).
- `run`/`pipeline` exit 0 unless a tier produced no result (1: error, timeout, Jenkins `NOT_RUN`) or a hosted run was
  refused (3). `--fail-on-differs` also exits 2 for differs/inconclusive. `pipeline` skips examples whose static
  validation failed (exit 1; `--continue-on-invalid` runs them anyway).
- A Jenkins reference recorded for another `--branch` or Jenkinsfile version is not used: re-run the `jenkins` tier
  with the same `--branch` before comparing.
