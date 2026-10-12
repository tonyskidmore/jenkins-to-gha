# j2gha architecture

`j2gha` implements the mechanism described in [mechanism.md](mechanism.md) as six harness stages over a corpus of
real-world Jenkins pipelines (`examples/NNN`). Every stage is a CLI sub-command, writes JSON artifacts into the
example directory and owns one marker-delimited section of the example `README.md`, so stages are idempotent and
can be re-run independently.

```text
                        github.com code search (crawler skill)
                                       │
                                       ▼
 examples/NNN/Jenkinsfile + source.json + README.md (citation, score /10)
                                       │
 ┌─────────────────────────────────────┼────────────────────────────────────────────────────────────────┐
 │ 1 analyze   Groovy AST (Jenkins' Groovy 2.4, Docker)  ─▶ IR (j2gha/ir.py) ─▶ inventory, findings,   │
 │             Jenkins toJson/validate (JCasC controller)     hard gates, coverage, difficulty 0-100    │
 │ 2 convert   IR ─▶ deterministic generator ─▶ gha/workflow.yml (SHA-pinned*) + migration-report.md   │
 │ 3 validate  actionlint (+shellcheck SAST), zizmor (security), j2gha policy                           │
 │ 4 run       jenkins: localised Jenkinsfile on disposable controller ─┐                               │
 │             act:     converted workflow variant in Docker            ├─▶ trace comparison per stage  │
 │ 5 run       selfhosted: JIT runners (real GitHub, 0 minutes)         │ (equivalent/differs/inconcl.) │
 │             hosted:     GitHub-hosted runners (budget guard)         ┘                               │
 │ 6 budget    minutes used vs included (billing API or jobs-API tally); guard refuses risky runs       │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

\* Actions are pinned to commit SHAs when a GitHub token can resolve them; otherwise they keep their version tags.

## Stages

| # | Stage | Command | What it does |
|---|---|---|---|
| 0 | Corpus | `j2gha crawl --count N` | GitHub code search across 17 pipeline styles. Licence filter, de-duplication, AST-based style detection, 0-10 score ([docs/scoring.md](scoring.md)), coverage-driven selection → `examples/NNN/{Jenkinsfile,README.md,source.json}` |
| 1 | Analysis | `j2gha analyze` | Groovy AST (Jenkins-bundled Groovy 2.4) + Jenkins Declarative model (`toJson`/`validate`) → IR, step inventory, findings, hard gates, weighted mapping coverage, **migration difficulty 0-100**. Written into each example README. |
| 2 | Conversion | `j2gha convert` | IR → `gha/workflow.yml` (actions SHA-pinned when a GitHub token can resolve them, least-privilege permissions) + `gha/migration-report.md` (every construct: mapped / approximated / manual / dropped, with source line, plus the Jenkins and GitHub Actions docs pages for each) |
| 3 | Static validation | `j2gha validate` | actionlint (structure + shellcheck SAST of the converted shell), zizmor (security), j2gha policy checks including structural checks on GitHub contexts, `needs` references and expression functions |
| 4 | Local execution | `j2gha run --tier jenkins,act` | Localised original on the disposable JCasC controller (auto-repaired from Jenkins' own errors) and the converted workflow on act. **Trace mode** compares per-stage step sequences and the stage order the Jenkinsfile fixes (parallel branches may interleave); **full mode** runs the real commands and compares the outcome. `--branch` and `--param NAME=VALUE` pin the same scenario on both sides; an edited workflow model is refused unless `--edited-model` (mutation tests). |
| 5 | Real GitHub Actions | `j2gha run --tier selfhosted` / `--tier hosted --yes` | Workflow pushed to a throw-away orphan branch in this repo. *selfhosted*: ephemeral JIT runners in local Docker (0 minutes). *hosted*: GitHub-hosted runners behind the budget guard. Logs are collected and compared, then the branch is deleted. |
| 6 | Minutes monitoring | `j2gha budget` | Actions minutes used vs included for the owner (user or organization) of the repository runs go to. Hosted runs are refused without complete billing data, beyond the remaining allowance (minus a 20% reserve and minutes reserved by runs not yet reconciled), or beyond the per-run cap. |

## Components

| Path | Responsibility |
|---|---|
| `j2gha/crawl/` | Style-targeted GitHub code search, licence/duplicate filtering, scoring, coverage-driven selection, example writer |
| `docker/jenkins/` | Controller image: `jenkins/jenkins:lts-jdk21` (2.580.1) + plugins + JCasC + the Groovy AST dumper + the toolchain real `sh` steps need (Maven, Node, make, Python, Docker CLI, Xvfb/Xvnc) |
| `docker/act/`, `docker/act-runner/`, `docker/runner/` | act CLI image, and the job-container images for act (`catthehacker/ubuntu:act-latest`) and the JIT self-hosted runners (`ghcr.io/actions/actions-runner`). The two runner images are harness-built, not pulled: they add the Jenkins image's toolchain for parity, so a full-mode difference is less likely to be a missing tool. The images are still different distributions with different package versions (Python 3.13 on the Jenkins image against 3.12 on the runner images, for example), so an environmental cause is not ruled out. Every base is digest-pinned and recorded in the `j2gha.base-image` label |
| `docker/jenkins/groovy/ast_dump.groovy` | Groovy CONVERSION-phase AST → JSON call tree with line/column provenance |
| `j2gha/analysis/` | AST walking, Declarative/scripted interpretation into the IR, step catalog, findings, difficulty scoring |
| `j2gha/rules/steps.yaml` | The organisational mapping policy: step → category (direct/policy/redesign/dynamic/noop), risk weight, GHA target |
| `j2gha/convert/` | Expression translation (`when`, Groovy conditions), workflow generation, SHA pinning |
| `j2gha/validate/` | actionlint, zizmor, policy checks, structural context checks (`contexts.py`) |
| `j2gha/jenkins/` | Controller lifecycle + REST client, localisation (make executable locally), execution |
| `j2gha/runners/` | Execution variants (trace/full × act/selfhosted/hosted), act runner, tier orchestration |
| `j2gha/gha/` | Orphan-branch remote runs, JIT runner pool, minutes budget guard |
| `.claude/skills/` | Optional agent skills (Claude Code); the CLI does not need an agent, see `docs/AI.md` |
| `examples/NNN/` | The corpus: `Jenkinsfile`, `README.md` (citation and every stage's results), `source.json`, and the generated `analysis/`, `gha/` and `runs/`. `examples/000` is the hand-written walkthrough, `examples/1NN` the twins |
| `tests/` | pytest suite (runs without Docker using committed AST fixtures; `-m e2e` adds the walkthrough end to end) |
| `docs/`, `docs/video/` | Design and user documentation; source projects for the walkthrough videos (scripts, real captures, screenshots) |
| `.docs/` | Downloaded reference docs (gitignored; `j2gha docs fetch`, see [documentation.md](documentation.md)) |

## Key design decisions

**Parser parity over convenience.** Jenkins compiles Jenkinsfiles with Groovy 2.4.21 (bundled in `jenkins.war`).
The AST dumper runs on exactly that jar inside the controller image, so "parses here" means "parses in Jenkins".
tree-sitter grammars were evaluated and rejected (the bundled grammar fails on `def`/`return`). Jenkins' own
Declarative model is fetched from the controller for validation and cross-checked against the IR.

**IR from the Groovy AST, validated by Jenkins.** The Declarative JSON from `toJson` lacks line numbers, drops
`@Library` and truncates one-line `script{}` blocks, so the IR is interpreted from the Groovy call tree (with
provenance) and Jenkins' model is used as the authority on validity (`JenkinsValidationFailed`, `ModelDiscrepancy`
findings).

**Job planning.** Consecutive stages sharing an agent become one job (Jenkins stages share a workspace; GHA jobs do
not); the stages of one scripted `node {}` share its agent and so its job. Parallel branches, matrices, stages with
their own agent and `input`-gated stages become separate jobs with `needs`. A parallel or matrix stage keeps its own
directives: its `when`, `environment` and `options` wrap every branch/cell job, its `input` becomes one approval job
before the fan-out and its `post` one fan-in job after it (later stages need both the branches and that job); matrix
cell-level `environment`/`options`/`input`/`tools` apply to every cell. Pipeline `post` goes into the last step(s) of
a single job or a final `if: always()` job whose steps each carry an explicit status function (a job-level
`always()` does not reach its steps, and a failing post step must not skip `cleanup`). The success condition is
`!failure() && !cancelled()`, because `success()` is false when a needed job was skipped.

**Workspace hand-off.** Splitting a pipeline into jobs would give up Jenkins' shared workspace, so it is handed on
where Jenkins shares it. `generator._workspace_handoff` picks the jobs whose stages run on the pipeline agent (no agent
of their own, or `reuseNode true`); `convert/workspace.py` plans and generates the rest. Every such job that changes
the workspace (a *producer*) ends by uploading the snapshot after it as a tar (`j2gha-ws-<job>`: modes, symlinks,
empty directories and `.git` kept) when a later job restores it, and starts from the snapshot before it instead of a
checkout: that of its nearest producers. After a `parallel`, the branches - which all started from one snapshot - are
*merged*: the first branch's snapshot is extracted and each later branch's *own changes* are replayed onto it, in job
order. Each branch that runs concurrently with another records the snapshot it starts from (a manifest of every
entry's type, mode and content digest or link target) and hands on its change list with its snapshot: entries added or
changed (content, mode, type, link target) and removed, directories included. So no merge needs the snapshot the
branches started from - one producer's, itself a merge (a `parallel` straight after another) or the checkout (a
`parallel` first stage). A branch that leaves a path alone never reverts another branch's change; a path two branches
change takes the later branch's version, and a branch that removes a directory removes what an earlier branch put
in it. The nearest workspaces are always downloaded. A job skipped at job level made no upload: the workspaces it
would have started from are downloaded instead (`continue-on-error` downloads that run only when the nearer ones
failed, each producer once, at most `MAX_HANDOFF_FALLBACKS` per job; a cut is reported). The merge step decides at
run time from what was downloaded: the workspaces no other downloaded one descends from (`J2GHA_WS_LINEAGE`). It
clears the job's own files first (act copies the repository into every job). Hard links are kept: a changed file
takes its whole link group (as the branch left it) into the change list, so a new, removed or renamed name is relinked.
The merge accounts for every producer along the fallback chain it actually uses: a missing workspace must belong to a
skipped job, whose own nearest producers are then accounted for. A producer the job needs directly has a known
result - if it ran but its workspace did not arrive, the merge fails instead of restoring an older workspace; any
other producer's result is not visible to the job, so its missing workspace is taken as skipped, with a warning. Matrix cells, `beforeInput` gate jobs and the pipeline post job restore but do not hand on. Unsupported
cases fail rather than pass: the steps need bash and GNU tar, findutils and coreutils (a busybox/Alpine job
container is a manual item in the migration report); an entry the job's user cannot read fails the hand-on; a
branch without a change list fails the merge; planning refuses concurrent producers that start from different
snapshots. The migration report's *Workspace hand-off* section lists the requirements and what is approximated. Not done: `agent none` pipelines (no shared workspace in Jenkins either), non-Linux pipeline
agents, and jobs with their own agent. Turn it off with `J2GHA_WORKSPACE_HANDOFF=0`. The steps are conversion-only
(`role: handoff`), so trace variants are unchanged; `validate/contexts.py` (`handoff-source`) checks that a job only
restores workspaces of jobs it needs. A parallel split stays `approximated`: concurrent branches still do not see each other's files. The computed pipeline `environment {}` is
evaluated again in every job that reads it (job outputs cannot cross a chain of `needs`), so a non-deterministic value
can differ between jobs.

**Scripted structure.** `node {}` pipelines keep statements outside named stages at their source position (unnamed
segments), re-apply wrappers that enclose stages (`dir`, `withEnv`, `withCredentials`, `timeout`, `retry`, ...) to
the enclosed stages' steps, and give `catch` bodies failure-only conditions. What cannot be represented is listed in
the migration report's *Interpretation notes*.

**Conditions against `env`, evaluated once.** `when` and translatable `if` statements compile to `if:` expressions
on the `env` context, with Jenkins-compatible variables (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`, `CHANGE_TARGET`,
`BUILD_NUMBER`, ...) defined at workflow level. This mirrors Jenkins semantics and lets the harness pin the scenario
for differential runs. A stage's `when` is evaluated once, by a *stage entry* step (`echo run=true >>
$GITHUB_OUTPUT`) whose output the stage's steps test, as Jenkins does - re-evaluating an env-based condition per step
would see variables the stage itself changes; stage `post` conditions anchor on the same step. Steps follow Jenkins'
order: options wrappers, `input` (unless `beforeInput`), `when`, `environment`, steps, `post`. A stage `input` becomes
the job's protected `environment`, entered before any step runs; with `beforeInput true` that would ask for approval of
a stage that is skipped, so the `when` is decided first, once, in a small *gate* job (same checkout and pipeline
environment as the stage) and the stage's own job - which carries the `environment`, so its environment secrets stay
available - has `if: needs.<stage>-gate.outputs.run == 'true'`: a skipped job asks nobody, and no job evaluates the
condition a second time. Jobs that need a possibly skipped job get `!failure() && !cancelled()`. A *parallel/matrix*
stage's `input` stays a separate approval job (one approval, not one per branch), so the branch jobs do not see
environment-scoped secrets. Every generated workflow is also checked structurally (`validate/contexts.py`: job-level
`if` contexts, `needs.*` references, step-env scope, expression functions, skip propagation, re-evaluated gate
decisions), so these rules hold for combinations the tests did not think of (`tests/test_contexts.py`).
Glob conditions follow Jenkins' Ant matcher (`*` stays inside one path segment, `?` is one character): exact where
GitHub's `contains`/`startsWith`/`endsWith` can say so, `approximated` for `prefix/*` (which also matches deeper
paths), and a manual gate for the rest - GitHub expressions have no regex, substring or length. A bare `params.X` is
Groovy truth by the declared type: `== 'true'` for a `booleanParam`, non-empty for a string (the string `"false"` is
true); `.trim()` is not translatable. A script `if` whose branches hold several steps is decided once (a step may
change the variable it tests) and the steps test that decision. The decision is two steps (`taken=true` when the condition
holds, `taken=false` when the first was skipped) that carry the same `env:` as the steps they decide for, because a
step's `if:` reads that step's own `env:` (verified on GitHub); a value only the shell computes cannot be read there and
becomes a manual gate. A gated stage's post actions, like its jobs, follow the gate's decision.
`changeRequest` filters (`target`, `branch`, `author`, `title`, ...) translate with their comparator; REGEXP
patterns translate when they are a literal, `prefix.*`, `.*suffix`, `.*part.*` or a literal alternation (Java
`matches()` is a whole-value match). Anything else, including `changeset`/`changelog`, becomes a repository variable
`vars.J2GHA_WHEN_L<line>` that states the condition's value ('true'/'false'). Unset, it takes the value that keeps
the stage *off* where it sits - false when used positively, true under an odd number of `not`s - so the stage runs
only where it would run whatever that condition's value: never a silent `true`, and never widened by a `not`.

**Runtime environment values.** `environment { X = sh(returnStdout: true) }` and GStrings referencing other
variables are evaluated by the shell at runtime: pipeline-level ones in a step writing `$GITHUB_ENV`, stage-level
ones exported before each run step (preserving Jenkins' stage scoping). `withEnv` keeps single-quoted values
literally (Jenkins does not expand them either), exports interpolated ones (`"X=${env.Y}"`, `'X=' + y`) in the
shell, and turns `PATH+NAME=dir` into a `PATH` prefix.

**Shell semantics.** Run steps use `bash -e -o pipefail`. `retry(n)` writes the script to a file and runs every
attempt as its own process with the same options, keeping the last exit status (inside `if (...)` bash would ignore
`set -e` and report an earlier failing command as success).

**Localisation by AST range, not regex.** The localiser rewrites exact source ranges (agents → `any`,
`node('label')` → `node('built-in')`, triggers/`@Library`/unresolvable imports removed, and options/parameters
whose value comes from a stubbed import class removed, since plugin describables cannot coerce `J2ghaAny`) and
appends a block that
shadows steps with script-level methods (CpsScript resolves script methods before steps). Appending, rather than
prepending, and padding every in-place edit to the line count of the span it replaces (a multi-line `agent {}` becomes
`agent any` plus blank lines), keeps Jenkins' error line numbers identical to the original file, which the
auto-repair loop relies on.

**Auto-repair loop.** Jenkins' own validation and runtime errors drive repairs, up to eight attempts: invalid
options/parameters/tools removed, empty stages filled, empty directives dropped, missing DSL methods stubbed,
undefined plugin/library globals replaced with permissive `J2ghaAny` objects (a script-level `def x` that is unset
when read is promoted in place to a `@Field` stub), bare environment values quoted. Every repair is recorded in
`runs/jenkins-<mode>/result.json` and the README. A repair that would leave the localised script unchanged is not
applied: it is recorded as `ineffective` and flagged with ⚠️ in the README instead of being reported as applied.

**Trace equivalence.** See [mechanism.md](mechanism.md#5-test-with-differential-execution-the-validation-pyramid);
what each verdict does and does not establish is in [mechanism.md](mechanism.md#what-the-verdicts-establish).
Markers carry Jenkins' `STAGE_NAME` semantics, including implicit `Declarative: Checkout SCM`, `Declarative: Post
Actions` and GString stage names evaluated per matrix cell (the GHA marker lets the shell expand the same variables).
Order is significant within a stage except where the workflow model shows the stage's steps run concurrently (matrix
cells, scripted `parallel` branches, a stage split across jobs); order *between* stages is the Jenkinsfile's partial
order (`trace.stage_order`: sequential stages are ordered, parallel branches are mutually unordered but each keeps its
own sequence, matrix inner stages interleave across cells; scripted pipelines declare no structure, so only per-stage
sequences are compared). No events on either side, runs that end differently behind matching traces, a Jenkins
reference that did not run, one recorded for another Jenkinsfile version, scenario or localiser version, or (full mode)
two outcomes with no stage or job data on either side are *inconclusive*, never *equivalent*.

**Scenarios.** Both sides are pinned to a branch (`--branch`) and, optionally, to parameter values
(`--param NAME=VALUE`, repeatable): a Jenkins build parameter and an override of the workflow `env` in the execution
variant. Only declared parameters can be set (anything else is refused before a run); on the Jenkins side the job
defines the parameters in its XML so exactly one build runs, and a pipeline whose parameters cannot be defined up front
falls back to a registration build that is recorded as a `register` attempt. The parameters are part of the scenario in
every run record, so a reference run with other values is refused. Execution variants also give the converted run what the
Jenkins reference ran with: `JOB_NAME`/`JOB_BASE_NAME` are the Jenkins job (`ex-<id>-<mode>`, not `github.workflow`), and an
undeclared upper-case property the localiser stubbed (it reads `j2gha-stub` on Jenkins) gets that value in the variant's `env`
(`variants.stubbed_properties`). When the Jenkins reference had no Docker (the localiser stubbed `withDockerContainer`, so `docker.image().inside`
and `agent { docker | dockerfile }` ran their steps directly), full variants drop the converted job's `container`, its
`dockerfile` image build and the `docker run` step wrappers, so those steps also run on the runner itself
(`variants.reference_had_docker`, on the jobs the generator marks `_j2gha.run_without_docker`).

**Provenance.** analyze stamps the AST and `analysis.json` with the Jenkinsfile's sha256; convert stamps
`conversion.json` with it and the workflow model's hash; run records carry the Jenkinsfile hash, the scenario, the
localiser version, the images used (`runners.images.image_provenance`) and the hash of the model *that was executed*
(not the one `convert` recorded). `convert` re-parses/re-analyses a changed Jenkinsfile, the localiser refuses a stale
analysis, the GHA tiers refuse a stale conversion - including a `workflow.model.json` edited after `convert` - a
report-only result removes the earlier workflow, and the README/summary mark run records of an earlier version (or of
another localiser version) as stale (not counted). A deliberate mutation test runs an edited model with
`run --edited-model`; such a record is marked `edited_model`, shown as stale and never counted.

**Structural checks.** The policy checks include `validate/contexts.py`, which every generated workflow must pass: a
job-level `if` may only read `github`, `needs`, `vars` and `inputs`; `needs.<job>` must name a direct need; an `env:`
entry cannot read a sibling entry of the same mapping (a step's `if:` can read the step's own `env:`); only GitHub's
expression functions are used; a job after a possibly skipped job has a status function; and a gated stage's condition
is evaluated by its gate job only. `tests/test_contexts.py` runs them over the committed corpus and a cross product of
the constructs the converter combines (`beforeInput`, parallel/matrix, stage `post`, environments, script `if`, `dir`,
`writeFile`, checkout subdirectory, first-stage position); a new construct that can combine with the others belongs in
its dimensions.

**Exit status.** `validate` fails when actionlint or the j2gha policy fails or a scanner cannot run (zizmor findings
are advisory and shown separately). `pipeline` does not execute examples whose validation failed
(`--continue-on-invalid` overrides). `run`/`pipeline` exit 1 when a tier produced no result (error, timeout, Jenkins
`NOT_RUN`), 3 when a hosted run was refused, 2 with `--fail-on-differs` when a comparison differed or was
inconclusive, else 0: a converted workflow that runs and fails is a result, judged by the comparison.

**Cost control.** Trace variants force `ubuntu-latest` (no Windows/macOS multipliers), drop containers and services,
and cap job timeouts at 5 minutes. The hosted tier estimates billable minutes (each job rounded up; matrices expanded
exactly by GitHub's include/exclude rules, or counted as 256 jobs and refused when built from expressions) and asks
the budget guard. The guard decides against the billing owner of the target repository (user or organization
billing usage, public repositories are free on standard runners), refuses incomplete usage data unless
`J2GHA_ALLOW_INCOMPLETE_USAGE=1`, and reserves the worst case in a locked ledger before dispatch, reconciled after
the run. A run interrupted while monitoring (error, Ctrl-C) is cancelled and stays a pending reservation;
`.j2gha/remote-runs/` records in-flight runs. The self-hosted tier is the default real-GitHub check, at zero hosted
minutes.

## Security posture

- The disposable controller listens on 127.0.0.1 only, uses a local-only admin password, fake credentials and
  pre-approved (non-sandboxed) scripts. It must never be exposed or pointed at real credentials.
- Third-party build scripts run only in containers. Neither the Jenkins controller nor act job containers receive
  the Docker socket unless explicitly requested (`run --docker`); only job-container options on an allowlist
  (`--user`, `-e NAME=value`, `--workdir`, ...) are kept in execution variants; everything else (mounts however
  spelled - `-v x`, `-vx`, `--volume=x`, `--mount` - `--privileged`, `--network`, unknown options) is dropped and
  recorded.
- Converted pipelines never receive the operator's credentials: every `secrets.*` reference in an execution variant is
  replaced by the fake value the Jenkins reference's fake credential has, act gets no token (full mode fetches the
  public source repository on the host, anonymously), and a Jenkins credential id is never turned into a reserved `GITHUB_*`
  secret name (`github_token` becomes `JENKINS_GITHUB_TOKEN`). GitHub-issued runtime credentials are a different matter:
  on the self-hosted and hosted tiers every job gets GitHub's automatic `GITHUB_TOKEN` (scoped by the workflow's
  `permissions: contents: read`; `actions/checkout` uses it), and `run --environments` adds the harness's own random
  `J2GHA_ENV_CANARY` secret to check that environment secrets arrive.
- The Jenkins controller is shared state: harness processes take an exclusive lock (`.j2gha/jenkins.lock`) and a
  second one fails fast, naming the holder.
- Remote runs use orphan branches that contain only the generated workflow, deleted after each run. Generated
  workflows use `permissions: contents: read` and `persist-credentials: false`, and pin actions to commit SHAs when a
  GitHub token is available to resolve them; otherwise an action keeps its version tag, which the policy check reports
  as a warning (`pin-actions`), not an error.
- Example files are only collected from repositories with a detected licence (unless `--allow-unlicensed`), and every
  README carries the citation.

## Known limitations (and where to extend)

The process for adding or changing a rule is in [extending.md](extending.md).

| Limitation | Effect | Extension point |
|---|---|---|
| Limited Groovy dataflow | An `if`/`else if` chain in `script{}` that only assigns string literals (`target = 'pro'`) or calls `error` becomes one bash step exporting the variable to `$GITHUB_ENV` and job outputs, so a later `when { expression { target == 'pro' } }` reads `env.target` (example 006). Other assignments carry their value the same way when it is a plain string expression: `x = sh(returnStdout: true)[.trim()]` (the traced `sh` step captures its output), literals, `env`/`params`, top-level constants, earlier variables, `+`, `.take(n)`, simple GStrings and `pwd()` (`generator._carry_assignment`; twins 106, 114, 119). A name that is an environment variable or parameter is left alone, since a Groovy variable is not in the environment of Jenkins' `sh` steps. Values built by dynamic Groovy (closures, loops, collections, `replaceAll`) are still not propagated, and a `when` on them becomes an opt-in `vars.J2GHA_WHEN_L<n>` gate. A later job sees a carried value only where it reads `env.<var>` (wired through job outputs). | Extend `generator._bash_value` to more constant-foldable expressions. |
| Dynamic fan-out | `parallel` over a runtime-built map and stages created in loops (hard gates) are only partially converted. Examples 001 and 002 show low trace similarity, as predicted by their difficulty scores. | Generate a planning job that emits a bounded JSON matrix (`fromJSON`). |
| Shared-library internals | Library steps are stubbed: the trace proves the calls happen, not what they do. Library templates run with a permissive configuration object. | Crawl and analyse the library repository; map library steps to composite actions via `rules/steps.yaml`. |
| Plugin-specific runtime objects | Objects such as `Artifactory.server(...)` are replaced by permissive `J2ghaAny` stubs, so behaviour that depends on their return values is not reproduced. | Add plugins to `docker/jenkins/plugins.txt` where they can run offline. |
| Workspace hand-off between jobs | The pipeline workspace is handed on between jobs as a whole (a tar per job), which costs an upload and a download per split and counts toward artifact storage; concurrent branches hash their whole workspace twice (start and end) to find their own changes, which is slow for very large workspaces. Concurrent parallel branches do not see each other's files while they run, and a path two of them change takes the later branch's version; a change of timestamps alone is not handed on; matrix cells' changes are not handed on; Windows/macOS pipeline agents and busybox/Alpine job containers get no working hand-off (the latter fail at the hand-off steps). | Hand on only the paths later stages read (needs a file-level dataflow analysis); a Windows variant of the scripts. |
| Approval (`input`) | The protected `environment` is on the stage's job (parallel/matrix: on one approval job, so branch jobs do not see environment-scoped secrets); input parameters are not supported. Execution variants remove `environment` unless `run --environments` (selfhosted/hosted) keeps it as `j2gha-<name>`: the run is then checked to enter exactly the environments of the stages whose `input` Jenkins reached, and each environment job checks that the environment's canary secret is visible. The approval itself is never exercised: the harness creates its environments without required reviewers (a private repository only gets them on GitHub Enterprise; a public one, such as this, can have them). A `beforeInput` gate decides `when` in the restored pipeline workspace (in a fresh checkout when the stage has its own agent). | Required reviewers on the `j2gha-*` environments of a public repository (hosted runners only) for live approval tests. |
| Glob and string conditions | Jenkins' `branch`/`tag` GLOB is Ant matching (`*` stays inside a path segment): exact for the shapes GitHub's `contains`/`startsWith`/`endsWith` can express, `approximated` for `prefix/*` (also matches deeper paths), a manual gate otherwise. GitHub's `==`, `startsWith` and friends ignore case, Jenkins' do not, so even translated `expression` conditions are only approximated. A shell-computed stage/wrapper value cannot be read by a step `if:` and becomes a manual gate. | None cheap: GitHub expressions have no regex, substring or case-sensitive compare. |
| `post { unstable/changed/fixed/regression }` | Dropped, because GHA has no UNSTABLE result and no previous-run status. | Query the previous run's conclusion through the REST API in a final job. |
| Scripted pipelines: stage order | Scripted pipelines declare no stage structure, and stages emitted by several jobs are treated as concurrent, so their steps may reorder without a verdict change. | Derive an order from the scripted `node`/`stage` nesting. |
| Trace markers carry step kinds | A marker names the stage and the step kind, not the command: trace equivalence is control-flow fidelity, not command or artifact equivalence. Full mode compares test cases and the set of archived files, but not their content (builds are not reproducible) and not other outputs (HTML reports, deployments). | Per-example content rules for files that are expected to be reproducible. |
| Trace mode stubs returns | `sh(returnStdout: true)` returns `''`, `readJSON` returns an empty config and library objects are truthy, non-empty `J2ghaAny` stubs, so Groovy branching on them may take a different path than production. When that ends in the pipeline's own `error()`, the comparison is reported *inconclusive* rather than *differs* (examples 017, 018). | Record real outputs in a full-mode run and replay them in trace mode. |
| Full mode environment | Real commands need toolchains, credentials and services that the disposable environment does not provide; failures are usually environmental, not conversion bugs. | Per-example `j2gha.yml` overrides (images, services, fake endpoints). |
| Hosted tier | Implemented and budget-guarded, but must be started by a human, because it spends account minutes. | `uv run j2gha run <ids> --tier hosted --yes --max-minutes N`. |
